import json
import sqlite3
import threading
from pathlib import Path
from typing import List, Optional

from app.trace.models import NL2SQLTrace
from app.trace.store import TraceStore
from app.trace.query import TraceQuery


class SQLiteTraceStore(TraceStore):
    def __init__(self, db_path: str, timeout: float = 5.0):
        self.db_path = str(db_path)
        self.timeout = timeout
        self._lock = threading.RLock()
        self._conn: sqlite3.Connection | None = None

        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(
                self.db_path,
                timeout=self.timeout,
                check_same_thread=False,
            )
            self._conn.row_factory = sqlite3.Row
            self._configure_connection(self._conn)

        return self._conn

    def _configure_connection(self, conn: sqlite3.Connection) -> None:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def __enter__(self):
        self._connect()
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    def _init_db(self) -> None:
        with self._lock:
            conn = self._connect()
            conn.execute("""
                CREATE TABLE IF NOT EXISTS nl2sql_traces (
                    trace_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,

                    raw_query TEXT,
                    normalized_query TEXT,

                    candidate_signals_json TEXT NOT NULL DEFAULT '[]',
                    rag_matches_json TEXT NOT NULL DEFAULT '[]',
                    graph_trace_json TEXT NOT NULL DEFAULT '{}',

                    selected_tables_json TEXT NOT NULL DEFAULT '[]',
                    dropped_tables_json TEXT NOT NULL DEFAULT '[]',

                    estimated_tokens INTEGER NOT NULL DEFAULT 0,
                    confidence REAL,

                    generated_sql TEXT,
                    sql_valid INTEGER,
                    sql_validation_errors_json TEXT NOT NULL DEFAULT '[]',

                    error_type TEXT,
                    error_message TEXT,

                    latency_ms_json TEXT NOT NULL DEFAULT '{}',
                    metadata_json TEXT NOT NULL DEFAULT '{}'
                )
            """)
            conn.commit()

            self._ensure_column(
                conn,
                "nl2sql_traces",
                "last_generated_sql",
                "last_generated_sql TEXT",
            )
            self._ensure_column(
                conn,
                "nl2sql_traces",
                "attempts_json",
                "attempts_json TEXT NOT NULL DEFAULT '[]'",
            )
            self._ensure_column(
                conn,
                "nl2sql_traces",
                "job_id",
                "job_id TEXT",
            )
            self._ensure_column(
                conn,
                "nl2sql_traces",
                "dialect",
                "dialect TEXT",
            )
            conn.commit()

    def _ensure_column(self, conn, table_name: str, column_name: str, column_sql: str) -> None:
        existing = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        }

        if column_name not in existing:
            conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_sql}")

    def _json_dumps(self, value, default) -> str:
        return json.dumps(value if value is not None else default, ensure_ascii=False)

    def _json_loads(self, value: str, default):
        if not value:
            return default
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default

    def save(self, trace: NL2SQLTrace) -> None:
        with self._lock:
            conn = self._connect()
            conn.execute("""
                INSERT OR REPLACE INTO nl2sql_traces (
                    trace_id,
                    created_at,
                    raw_query,
                    normalized_query,
                    candidate_signals_json,
                    rag_matches_json,
                    graph_trace_json,
                    selected_tables_json,
                    dropped_tables_json,
                    estimated_tokens,
                    confidence,
                    generated_sql,
                    last_generated_sql,
                    attempts_json,
                    job_id,
                    dialect,
                    sql_valid,
                    sql_validation_errors_json,
                    error_type,
                    error_message,
                    latency_ms_json,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trace.trace_id,
                trace.created_at,
                trace.raw_query,
                trace.normalized_query,
                self._json_dumps(trace.candidate_signals, []),
                self._json_dumps(trace.rag_matches, []),
                self._json_dumps(trace.graph_trace, {}),
                self._json_dumps(trace.selected_tables, []),
                self._json_dumps(trace.dropped_tables, []),
                trace.estimated_tokens,
                trace.confidence,
                trace.generated_sql,
                trace.last_generated_sql,
                self._json_dumps(trace.attempts, []),
                trace.metadata.get("job_id"),
                trace.metadata.get("dialect"),
                None if trace.sql_valid is None else int(trace.sql_valid),
                self._json_dumps(trace.sql_validation_errors, []),
                trace.error_type,
                trace.error_message,
                self._json_dumps(trace.latency_ms, {}),
                self._json_dumps(trace.metadata, {}),
            ))
            conn.commit()

    def get(self, trace_id: str) -> Optional[NL2SQLTrace]:
        with self._lock:
            conn = self._connect()
            row = conn.execute(
                "SELECT * FROM nl2sql_traces WHERE trace_id = ?",
                (trace_id,)
            ).fetchone()

        if row is None:
            return None

        return self._row_to_trace(row)

    def list_traces(self, query: TraceQuery) -> List[NL2SQLTrace]:
        with self._lock:
            conn = self._connect()
            
            where = []
            params = []

            if query.sql_valid is not None:
                where.append("sql_valid = ?")
                params.append(int(query.sql_valid))

            if query.error_type:
                where.append("error_type = ?")
                params.append(query.error_type)

            if query.job_id:
                where.append("job_id = ?")
                params.append(query.job_id)

            if query.dialect:
                where.append("dialect = ?")
                params.append(query.dialect)

            if query.created_after:
                where.append("created_at >= ?")
                params.append(query.created_after)

            if query.created_before:
                where.append("created_at <= ?")
                params.append(query.created_before)

            where_clause = ""
            if where:
                where_clause = "WHERE " + " AND ".join(where)

            sql = f"""
                SELECT * FROM nl2sql_traces
                {where_clause}
                ORDER BY created_at DESC, trace_id DESC
                LIMIT ? OFFSET ?
            """
            
            params.extend([query.limit, query.offset])
            
            rows = conn.execute(sql, tuple(params)).fetchall()

        return [self._row_to_trace(row) for row in rows]

    def _row_to_trace(self, row) -> NL2SQLTrace:
        sql_valid = row["sql_valid"]
        if sql_valid is not None:
            sql_valid = bool(sql_valid)

        return NL2SQLTrace(
            trace_id=row["trace_id"],
            created_at=row["created_at"],

            raw_query=row["raw_query"],
            normalized_query=row["normalized_query"],

            candidate_signals=self._json_loads(row["candidate_signals_json"], []),
            rag_matches=self._json_loads(row["rag_matches_json"], []),
            graph_trace=self._json_loads(row["graph_trace_json"], {}),

            selected_tables=self._json_loads(row["selected_tables_json"], []),
            dropped_tables=self._json_loads(row["dropped_tables_json"], []),

            estimated_tokens=row["estimated_tokens"] or 0,
            confidence=row["confidence"],

            generated_sql=row["generated_sql"],
            last_generated_sql=row["last_generated_sql"] if "last_generated_sql" in row.keys() else None,
            sql_valid=sql_valid,
            sql_validation_errors=self._json_loads(row["sql_validation_errors_json"], []),
            attempts=self._json_loads(row["attempts_json"] if "attempts_json" in row.keys() else "[]", []),

            error_type=row["error_type"],
            error_message=row["error_message"],

            latency_ms=self._json_loads(row["latency_ms_json"], {}),
            metadata=self._json_loads(row["metadata_json"], {}),
        )
