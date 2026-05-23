import json
import sqlite3
from pathlib import Path
from typing import List, Optional

from app.trace.models import NL2SQLTrace
from app.trace.store import TraceStore

class SQLiteTraceStore(TraceStore):
    def __init__(self, db_path: str):
        self.db_path = str(db_path)
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path)

    def _init_db(self) -> None:
        with self._connect() as conn:
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

    def _json_dumps(self, value) -> str:
        return json.dumps(value if value is not None else {}, ensure_ascii=False)

    def _json_loads(self, value: str, default):
        if not value:
            return default
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return default

    def save(self, trace: NL2SQLTrace) -> None:
        with self._connect() as conn:
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
                    sql_valid,
                    sql_validation_errors_json,
                    error_type,
                    error_message,
                    latency_ms_json,
                    metadata_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trace.trace_id,
                trace.created_at,
                trace.raw_query,
                trace.normalized_query,
                json.dumps(trace.candidate_signals, ensure_ascii=False),
                json.dumps(trace.rag_matches, ensure_ascii=False),
                json.dumps(trace.graph_trace, ensure_ascii=False),
                json.dumps(trace.selected_tables, ensure_ascii=False),
                json.dumps(trace.dropped_tables, ensure_ascii=False),
                trace.estimated_tokens,
                trace.confidence,
                trace.generated_sql,
                None if trace.sql_valid is None else int(trace.sql_valid),
                json.dumps(trace.sql_validation_errors, ensure_ascii=False),
                trace.error_type,
                trace.error_message,
                json.dumps(trace.latency_ms, ensure_ascii=False),
                json.dumps(trace.metadata, ensure_ascii=False),
            ))
            conn.commit()

    def get(self, trace_id: str) -> Optional[NL2SQLTrace]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM nl2sql_traces WHERE trace_id = ?",
                (trace_id,)
            ).fetchone()

        if row is None:
            return None

        return self._row_to_trace(row)

    def list_recent(self, limit: int = 50) -> List[NL2SQLTrace]:
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT * FROM nl2sql_traces
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,)
            ).fetchall()

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
            sql_valid=sql_valid,
            sql_validation_errors=self._json_loads(row["sql_validation_errors_json"], []),

            error_type=row["error_type"],
            error_message=row["error_message"],

            latency_ms=self._json_loads(row["latency_ms_json"], {}),
            metadata=self._json_loads(row["metadata_json"], {}),
        )
