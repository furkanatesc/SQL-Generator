import uuid
import pytest
from app.database import init_db, get_db_connection
from app import query_history_repository as repo


def _seed_conn(conn, cid, workspace_id):
    conn.execute(
        "INSERT INTO connections (id, connection_ref, workspace_id, name, dialect, "
        "environment, host, port, database, access_mode, auth_mode, max_rows, "
        "timeout_seconds, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (cid, cid, workspace_id, "n", "postgresql", "local", "h", 5432, "d",
         "read_only", "none", 1000, 2.0, "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
    )


def _seed_run(conn, cid, sql, status, created_at):
    conn.execute(
        "INSERT INTO query_runs (id, connection_id, sql, status, created_at) "
        "VALUES (?,?,?,?,?)",
        (uuid.uuid4().hex, cid, sql, status, created_at),
    )


@pytest.fixture(autouse=True)
def _db():
    init_db()
    with get_db_connection() as conn:
        conn.execute("DELETE FROM query_runs")
        conn.execute("DELETE FROM connections")
        _seed_conn(conn, "c1", "ws1")
        _seed_conn(conn, "c2", "ws2")
        _seed_run(conn, "c1", "SELECT a FROM t", "succeeded", "2026-01-01T10:00:00")
        _seed_run(conn, "c1", "SELECT b FROM t", "failed", "2026-01-02T10:00:00")
        _seed_run(conn, "c2", "UPDATE x", "recorded", "2026-01-03T10:00:00")
        conn.commit()
    yield
    with get_db_connection() as conn:
        conn.execute("DELETE FROM query_runs")
        conn.execute("DELETE FROM connections")
        conn.commit()


def test_list_all():
    assert len(repo.list_history(50, 0)) == 3


def test_filter_connection():
    assert len(repo.list_history(50, 0, connection_id="c1")) == 2


def test_filter_workspace_via_join():
    rows = repo.list_history(50, 0, workspace_id="ws1")
    assert len(rows) == 2 and all(r["workspace_id"] == "ws1" for r in rows)


def test_filter_status():
    assert len(repo.list_history(50, 0, status="failed")) == 1


def test_filter_date_range():
    rows = repo.list_history(50, 0, since="2026-01-02T00:00:00", until="2026-01-02T23:59:59")
    assert len(rows) == 1 and rows[0]["status"] == "failed"


def test_filter_text_search():
    rows = repo.list_history(50, 0, q="SELECT")
    assert len(rows) == 2 and all("SELECT" in r["sql"] for r in rows)


def test_paginate_and_count():
    assert repo.count_history() == 3
    assert len(repo.list_history(2, 0)) == 2
    assert len(repo.list_history(2, 2)) == 1


def test_history_row_shape_no_result_rows():
    r = repo.list_history(1, 0)[0]
    assert set(r.keys()) == {"id", "connection_id", "workspace_id", "sql", "status",
                             "row_count", "created_at"}


def test_summary_totals_and_by_status():
    s = repo.summary()
    assert s["total"] == 3
    assert s["by_status"] == {"recorded": 1, "succeeded": 1, "failed": 1}


def test_summary_respects_filter():
    s = repo.summary(connection_id="c1")
    assert s["total"] == 2 and s["by_status"]["succeeded"] == 1 and s["by_status"]["recorded"] == 0
