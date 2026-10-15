"""App database migrations (`SQLGEN_DB_PATH`, Sprint 32.3).

Version 1 is the baseline: the schema `app.database.init_db` used to create ad hoc on every
boot, moved here verbatim. It is idempotent (`IF NOT EXISTS` + `ensure_column`) so databases
created before 32.3 are adopted without data loss. Never edit a shipped migration; add a new
version instead (see docs/database-migrations.md).
"""
import sqlite3

from app.migrations.runner import Migration, ensure_column, validate_registry


def _baseline(conn: sqlite3.Connection) -> None:
    # Configs tablosu
    conn.execute("""
        CREATE TABLE IF NOT EXISTS configs (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
    """)
    
    # Jobs tablosu
    conn.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            file_path TEXT,
            natural_query TEXT,
            previous_sql TEXT,
            result_sql TEXT,
            error_message TEXT,
            error_code TEXT,
            dialect TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    
    # Backward compatibility for pre-migration jobs tables
    ensure_column(conn, "jobs", "dialect", "dialect TEXT")
    ensure_column(conn, "jobs", "previous_sql", "previous_sql TEXT")
    ensure_column(conn, "jobs", "error_code", "error_code TEXT")

    # Synonym Rules tablosu
    conn.execute("""
        CREATE TABLE IF NOT EXISTS synonym_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            term TEXT NOT NULL,
            normalized_term TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_name TEXT NOT NULL,
            confidence REAL NOT NULL DEFAULT 0.8,
            source TEXT NOT NULL DEFAULT 'manual',
            priority INTEGER NOT NULL DEFAULT 100,
            enabled INTEGER NOT NULL DEFAULT 1,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Trace Tablosu
    conn.execute("""
        CREATE TABLE IF NOT EXISTS query_traces (
            id TEXT PRIMARY KEY,
            job_id TEXT,
            natural_query TEXT,
            candidate_tables TEXT,
            selected_tables TEXT,
            estimated_tokens INTEGER,
            generated_sql TEXT,
            sql_valid INTEGER,
            error_message TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Feedback Tablosu (Sprint 27.3 — append-only)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL,
            verdict TEXT NOT NULL,
            category TEXT,
            note TEXT,
            corrected_sql TEXT,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_feedback_job_id ON feedback (job_id)"
    )

    # SQL Result Cache tablosu (Sprint 28.9)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sql_cache (
            cache_key        TEXT PRIMARY KEY,
            sql              TEXT NOT NULL,
            dialect          TEXT,
            schema_signature TEXT,
            created_at       TEXT,
            hit_count        INTEGER DEFAULT 0
        )
    """)

    # Sprint 30.1 — Workspace API. Standalone top-level container resource
    # (Phase 11); existing global tables are NOT retro-scoped yet.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS workspaces (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            slug        TEXT NOT NULL UNIQUE,
            description TEXT,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        )
    """)

    # Sprint 30.2 — Connection Registry API. Persistent connection profiles
    # (secret-by-reference; NEVER a raw secret column). Optional workspace link.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS connections (
            id              TEXT PRIMARY KEY,
            connection_ref  TEXT NOT NULL UNIQUE,
            workspace_id    TEXT,
            name            TEXT NOT NULL,
            dialect         TEXT NOT NULL,
            environment     TEXT NOT NULL,
            host            TEXT NOT NULL,
            port            INTEGER NOT NULL,
            database        TEXT NOT NULL,
            access_mode     TEXT NOT NULL,
            auth_mode       TEXT NOT NULL,
            secret_provider TEXT,
            secret_key      TEXT,
            max_rows        INTEGER NOT NULL,
            timeout_seconds REAL NOT NULL,
            created_at      TEXT NOT NULL,
            updated_at      TEXT NOT NULL
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_connections_workspace_id "
        "ON connections (workspace_id)"
    )

    # Sprint 30.3 — Schema Sync API. Per-connection schema snapshots + drift
    # (schema provided in the request; inert, no live introspection). Append-only.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_syncs (
            id                 TEXT PRIMARY KEY,
            connection_id      TEXT NOT NULL,
            signature          TEXT NOT NULL,
            previous_signature TEXT,
            drifted            INTEGER NOT NULL,
            structure_json     TEXT NOT NULL,
            drift_json         TEXT NOT NULL,
            created_at         TEXT NOT NULL
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_schema_syncs_connection_id "
        "ON schema_syncs (connection_id)"
    )

    # Sprint 30.4 — Query Run API. Inert ledger of SQL runs against a connection
    # (SQL + optional provided outcome). No live execution / secret resolution.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS query_runs (
            id              TEXT PRIMARY KEY,
            connection_id   TEXT NOT NULL,
            sql             TEXT NOT NULL,
            status          TEXT NOT NULL,
            row_count       INTEGER,
            columns_json    TEXT,
            rows_json       TEXT,
            truncated       INTEGER,
            execution_error TEXT,
            duration_ms     REAL,
            created_at      TEXT NOT NULL
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_query_runs_connection_id "
        "ON query_runs (connection_id)"
    )
    # Sprint 30.5 — query-history date-range/summary filters scan by created_at.
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_query_runs_created_at "
        "ON query_runs (created_at)"
    )

    # Sprint 30.6 — Feedback API. Query-run-scoped feedback (verdict + optional
    # category/note/corrected_sql). Distinct from the legacy 27.3 job feedback.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS query_run_feedback (
            id            TEXT PRIMARY KEY,
            query_run_id  TEXT NOT NULL,
            verdict       TEXT NOT NULL,
            category      TEXT,
            note          TEXT,
            corrected_sql TEXT,
            created_at    TEXT NOT NULL
        )
    """)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_query_run_feedback_query_run_id "
        "ON query_run_feedback (query_run_id)"
    )

    # Sprint 30.8 — AuthN. Managed hashed API keys (store hash + prefix only,
    # NEVER the raw key). Inert: does not yet govern verify_api_key.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL,
            key_prefix  TEXT NOT NULL,
            key_hash    TEXT NOT NULL UNIQUE,
            created_at  TEXT NOT NULL,
            revoked_at  TEXT
        )
    """)


def _job_worker(conn: sqlite3.Connection) -> None:
    """Sprint 32.4 — worker claim/heartbeat columns + persistent job logs."""
    ensure_column(conn, "jobs", "worker_id", "worker_id TEXT")
    ensure_column(conn, "jobs", "claimed_at", "claimed_at TEXT")
    ensure_column(conn, "jobs", "heartbeat_at", "heartbeat_at TEXT")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS job_logs (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id     TEXT NOT NULL,
            step       INTEGER,
            message    TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_job_logs_job_id ON job_logs (job_id, id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status_created_at ON jobs (status, created_at)")


APP_MIGRATIONS: tuple[Migration, ...] = (
    Migration(1, "baseline", _baseline),
    Migration(2, "job_worker", _job_worker),
)

validate_registry(APP_MIGRATIONS)
