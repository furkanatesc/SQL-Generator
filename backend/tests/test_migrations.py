"""Sprint 32.3 — Database Migration Strategy.

`app/migrations/` is a small forward-only, versioned migration runner for the two SQLite
databases (app DB and trace DB). Version 1 of each registry is the baseline: the schema
`init_db` / `SQLiteTraceStore` used to create ad hoc, applied idempotently so existing
databases are adopted without data loss.
"""
import json
import os
import sqlite3
from unittest.mock import patch

import pytest

from app.migrations import (
    APP_MIGRATIONS,
    TRACE_MIGRATIONS,
    Migration,
    ensure_column,
    inspect,
    migrate,
    validate_registry,
)
from app.migrations.__main__ import main as cli_main
from app.settings import get_settings

APP_TABLES = {
    "configs", "jobs", "synonym_rules", "query_traces", "feedback", "sql_cache", "workspaces",
    "connections", "schema_syncs", "query_runs", "query_run_feedback", "api_keys",
}
APP_INDEXES = {
    "idx_feedback_job_id", "idx_connections_workspace_id", "idx_schema_syncs_connection_id",
    "idx_query_runs_connection_id", "idx_query_runs_created_at", "idx_query_run_feedback_query_run_id",
}
TRACE_TABLES = {"nl2sql_traces", "traces"}


def _connect(path):
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def _names(conn, kind):
    return {
        r["name"]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type = ?", (kind,))
        if not r["name"].startswith("sqlite_")
    }


def _columns(conn, table):
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


def _versions(conn):
    return [r["version"] for r in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]


# --- registry ----------------------------------------------------------------------

def test_shipped_registries_are_valid():
    validate_registry(APP_MIGRATIONS)
    validate_registry(TRACE_MIGRATIONS)
    assert APP_MIGRATIONS[0].name == "baseline" and TRACE_MIGRATIONS[0].name == "baseline"


def _noop(conn):
    pass


@pytest.mark.parametrize(
    "registry",
    [
        (Migration(1, "a", _noop), Migration(3, "c", _noop)),  # gap
        (Migration(2, "a", _noop),),  # does not start at 1
        (Migration(1, "a", _noop), Migration(1, "b", _noop)),  # duplicate version
        (Migration(1, "a", _noop), Migration(2, "a", _noop)),  # duplicate name
        (),  # empty
    ],
    ids=["gap", "not-from-1", "dup-version", "dup-name", "empty"],
)
def test_invalid_registries_are_rejected(registry):
    with pytest.raises(ValueError):
        validate_registry(registry)


# --- runner --------------------------------------------------------------------------

def _create_t(conn):
    conn.execute("CREATE TABLE t (id INTEGER PRIMARY KEY)")


def _add_col(conn):
    conn.execute("ALTER TABLE t ADD COLUMN name TEXT")


def _boom(conn):
    conn.execute("CREATE TABLE half_done (id INTEGER)")
    raise RuntimeError("secret detail that must not be surfaced")


def test_inspect_fresh_db_is_version_zero(tmp_path):
    conn = _connect(tmp_path / "x.db")
    s = inspect(conn, (Migration(1, "t", _create_t),))
    assert (s.current, s.latest, s.pending, s.ahead) == (0, 1, [1], False)
    assert "schema_migrations" not in _names(conn, "table")  # read-only


def test_migrate_applies_in_order_and_records(tmp_path):
    conn = _connect(tmp_path / "x.db")
    reg = (Migration(1, "t", _create_t), Migration(2, "col", _add_col))
    s = migrate(conn, reg)
    assert (s.current, s.latest, s.pending, s.applied, s.error) == (2, 2, [], [1, 2], None)
    assert _versions(conn) == [1, 2]
    assert _columns(conn, "t") == {"id", "name"}
    row = conn.execute("SELECT name, applied_at FROM schema_migrations WHERE version = 2").fetchone()
    assert row["name"] == "col" and row["applied_at"]


def test_migrate_is_idempotent(tmp_path):
    conn = _connect(tmp_path / "x.db")
    reg = (Migration(1, "t", _create_t),)
    migrate(conn, reg)
    s = migrate(conn, reg)
    assert s.applied == [] and s.current == 1 and _versions(conn) == [1]


def test_failed_migration_rolls_back_and_stops(tmp_path):
    conn = _connect(tmp_path / "x.db")
    reg = (Migration(1, "t", _create_t), Migration(2, "boom", _boom), Migration(3, "col", _add_col))
    s = migrate(conn, reg)
    assert s.applied == [1]
    assert s.current == 1 and s.pending == [2, 3]
    assert s.error == "RuntimeError"
    assert "half_done" not in _names(conn, "table")  # DDL rolled back
    assert _columns(conn, "t") == {"id"}  # 3 never attempted
    assert _versions(conn) == [1]


def test_db_ahead_of_code_applies_nothing(tmp_path):
    conn = _connect(tmp_path / "x.db")
    migrate(conn, (Migration(1, "t", _create_t), Migration(2, "col", _add_col)))
    s = migrate(conn, (Migration(1, "t", _create_t),))  # older code
    assert (s.current, s.latest, s.ahead, s.applied, s.pending) == (2, 1, True, [], [])


def test_ensure_column_is_idempotent(tmp_path):
    conn = _connect(tmp_path / "x.db")
    _create_t(conn)
    ensure_column(conn, "t", "extra", "extra TEXT")
    ensure_column(conn, "t", "extra", "extra TEXT")
    assert _columns(conn, "t") == {"id", "extra"}


# --- baselines -------------------------------------------------------------------------

def test_app_baseline_on_empty_db(tmp_path):
    conn = _connect(tmp_path / "app.db")
    s = migrate(conn, APP_MIGRATIONS)
    assert s.error is None and s.pending == []
    assert _names(conn, "table") == APP_TABLES | {"schema_migrations"}
    assert APP_INDEXES <= _names(conn, "index")
    assert {"dialect", "previous_sql", "error_code"} <= _columns(conn, "jobs")


def test_app_baseline_adopts_legacy_db_without_data_loss(tmp_path):
    conn = _connect(tmp_path / "legacy.db")
    conn.execute(
        "CREATE TABLE jobs (id TEXT PRIMARY KEY, status TEXT NOT NULL, file_path TEXT, "
        "natural_query TEXT, result_sql TEXT, error_message TEXT, created_at TEXT NOT NULL, "
        "updated_at TEXT NOT NULL)"
    )
    conn.execute("INSERT INTO jobs VALUES ('j1', 'done', NULL, 'q', 'SELECT 1', NULL, 't', 't')")
    conn.execute("CREATE TABLE configs (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    conn.execute("INSERT INTO configs VALUES ('api_key', 'operator-key')")
    conn.commit()

    s = migrate(conn, APP_MIGRATIONS)

    assert s.error is None and s.current == len(APP_MIGRATIONS)
    assert {"dialect", "previous_sql", "error_code"} <= _columns(conn, "jobs")
    assert conn.execute("SELECT result_sql FROM jobs WHERE id = 'j1'").fetchone()[0] == "SELECT 1"
    assert conn.execute("SELECT value FROM configs WHERE key = 'api_key'").fetchone()[0] == "operator-key"


def test_trace_baseline_adopts_legacy_db(tmp_path):
    conn = _connect(tmp_path / "trace.db")
    conn.execute(
        "CREATE TABLE nl2sql_traces (trace_id TEXT PRIMARY KEY, created_at TEXT NOT NULL, "
        "metadata_json TEXT NOT NULL DEFAULT '{}')"
    )
    conn.execute("INSERT INTO nl2sql_traces (trace_id, created_at) VALUES ('t1', 'now')")
    conn.commit()

    s = migrate(conn, TRACE_MIGRATIONS)

    assert s.error is None
    assert _names(conn, "table") == TRACE_TABLES | {"schema_migrations"}
    assert {"last_generated_sql", "attempts_json", "job_id", "dialect"} <= _columns(conn, "nl2sql_traces")
    assert conn.execute("SELECT COUNT(*) FROM nl2sql_traces").fetchone()[0] == 1


def test_init_db_records_app_baseline(tmp_path, monkeypatch):
    from app.database import init_db

    monkeypatch.setenv("SQLGEN_DB_PATH", str(tmp_path / "fresh.db"))
    init_db()
    init_db()  # second boot is a no-op
    conn = _connect(tmp_path / "fresh.db")
    assert _versions(conn) == [m.version for m in APP_MIGRATIONS]
    assert conn.execute("SELECT COUNT(*) FROM synonym_rules").fetchone()[0] > 0  # seeds still run


def test_trace_store_records_trace_baseline(tmp_path):
    from app.trace.sqlite_store import SQLiteTraceStore

    store = SQLiteTraceStore(str(tmp_path / "t" / "trace.db"))
    store.close()
    conn = _connect(tmp_path / "t" / "trace.db")
    assert _versions(conn) == [m.version for m in TRACE_MIGRATIONS]


# --- startup warnings ------------------------------------------------------------------

def _warnings(monkeypatch, app_db, trace_db):
    monkeypatch.setenv("SQLGEN_DB_PATH", str(app_db))
    monkeypatch.setenv("NL2SQL_TRACE_DB_PATH", str(trace_db))
    get_settings.cache_clear()
    from app.startup_validation import validate_runtime_config

    with patch("app.startup_validation.get_config", return_value="db-key"):
        return {w.code: w for w in validate_runtime_config().warnings}


def test_up_to_date_dbs_raise_no_migration_warnings(monkeypatch, tmp_path):
    for name, reg in (("app.db", APP_MIGRATIONS), ("trace.db", TRACE_MIGRATIONS)):
        migrate(_connect(tmp_path / name), reg)
    w = _warnings(monkeypatch, tmp_path / "app.db", tmp_path / "trace.db")
    assert "DB_SCHEMA_AHEAD" not in w and "DB_MIGRATIONS_PENDING" not in w


def test_missing_trace_db_is_skipped(monkeypatch, tmp_path):
    migrate(_connect(tmp_path / "app.db"), APP_MIGRATIONS)
    w = _warnings(monkeypatch, tmp_path / "app.db", tmp_path / "nope" / "trace.db")
    assert "DB_MIGRATIONS_PENDING" not in w
    assert not (tmp_path / "nope").exists()  # inspection never creates files


def test_db_ahead_is_critical(monkeypatch, tmp_path):
    conn = _connect(tmp_path / "app.db")
    migrate(conn, APP_MIGRATIONS + (Migration(len(APP_MIGRATIONS) + 1, "future", _noop),))
    w = _warnings(monkeypatch, tmp_path / "app.db", tmp_path / "nope.db")
    assert w["DB_SCHEMA_AHEAD"].severity == "critical"
    assert "app" in w["DB_SCHEMA_AHEAD"].message
    assert str(tmp_path) not in w["DB_SCHEMA_AHEAD"].message


def test_pending_migration_is_critical(monkeypatch, tmp_path):
    _connect(tmp_path / "app.db").execute("CREATE TABLE configs (key TEXT PRIMARY KEY, value TEXT)")
    w = _warnings(monkeypatch, tmp_path / "app.db", tmp_path / "nope.db")
    assert w["DB_MIGRATIONS_PENDING"].severity == "critical"
    assert str(tmp_path) not in w["DB_MIGRATIONS_PENDING"].message


# --- CLI -------------------------------------------------------------------------------------

def test_cli_status_and_upgrade(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("SQLGEN_DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("NL2SQL_TRACE_DB_PATH", str(tmp_path / "trace.db"))

    assert cli_main(["status"]) == 0
    before = {d["db"]: d for d in json.loads(capsys.readouterr().out)}
    assert before["app"]["pending"] == [m.version for m in APP_MIGRATIONS]
    assert before["trace"]["exists"] is False
    assert not (tmp_path / "app.db").exists() or before["app"]["current"] == 0

    assert cli_main(["upgrade"]) == 0
    after = {d["db"]: d for d in json.loads(capsys.readouterr().out)}
    assert after["app"]["pending"] == [] and after["trace"]["pending"] == []
    assert after["app"]["current"] == len(APP_MIGRATIONS)


def test_cli_upgrade_fails_when_db_ahead(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("SQLGEN_DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("NL2SQL_TRACE_DB_PATH", str(tmp_path / "trace.db"))
    migrate(_connect(tmp_path / "app.db"), APP_MIGRATIONS + (Migration(len(APP_MIGRATIONS) + 1, "f", _noop),))
    assert cli_main(["upgrade"]) == 1
    assert cli_main(["status"]) == 0  # status only reports
    capsys.readouterr()


def test_cli_rejects_unknown_command(capsys):
    with pytest.raises(SystemExit):
        cli_main(["drop-everything"])
    capsys.readouterr()
