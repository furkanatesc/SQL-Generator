"""Trace database migrations (`NL2SQL_TRACE_DB_PATH`, Sprint 32.3).

Version 1 is the baseline: the schema `SQLiteTraceStore._init_db` used to create ad hoc,
moved here verbatim and idempotent so pre-32.3 trace databases are adopted. Never edit a
shipped migration; add a new version instead (see docs/database-migrations.md).
"""
import sqlite3

from app.migrations.runner import Migration, ensure_column, validate_registry


def _baseline(conn: sqlite3.Connection) -> None:
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
    ensure_column(conn, "nl2sql_traces", "last_generated_sql", "last_generated_sql TEXT")
    ensure_column(conn, "nl2sql_traces", "attempts_json", "attempts_json TEXT NOT NULL DEFAULT '[]'")
    ensure_column(conn, "nl2sql_traces", "job_id", "job_id TEXT")
    ensure_column(conn, "nl2sql_traces", "dialect", "dialect TEXT")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS traces (
            trace_id TEXT PRIMARY KEY,
            trace_type TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            created_at TEXT NOT NULL,
            job_id TEXT,
            request_id TEXT,
            dialect TEXT,
            sql_valid INTEGER,
            error_type TEXT
        )
    """)


TRACE_MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, "baseline", _baseline),
)

validate_registry(TRACE_MIGRATIONS)
