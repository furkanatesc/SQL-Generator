import pytest
from app.database import init_db, get_db_connection
from app import query_run_repository as repo


@pytest.fixture(autouse=True)
def _db():
    init_db()
    with get_db_connection() as conn:
        conn.execute("DELETE FROM query_runs")
        conn.commit()
    yield
    with get_db_connection() as conn:
        conn.execute("DELETE FROM query_runs")
        conn.commit()


def test_recorded_run_no_result():
    r = repo.create_query_run("conn1", "SELECT 1")
    assert r["status"] == "recorded"
    assert r["row_count"] is None
    resp = repo.row_to_response_dict(r)
    assert resp["result"] is None and resp["execution_error"] is None


def test_succeeded_run_with_result():
    r = repo.create_query_run("conn1", "SELECT id FROM t",
                              result={"columns": ["id"], "rows": [[1], [2]], "truncated": False})
    assert r["status"] == "succeeded" and r["row_count"] == 2
    resp = repo.row_to_response_dict(r)
    assert resp["result"]["columns"] == ["id"] and resp["result"]["rows"] == [[1], [2]]


def test_failed_run_with_error():
    r = repo.create_query_run("conn1", "SELECT bad", result={"execution_error": "boom"})
    assert r["status"] == "failed"
    resp = repo.row_to_response_dict(r)
    assert resp["execution_error"] == "boom" and resp["result"] is None


def test_list_filters_and_paginate():
    repo.create_query_run("conn1", "SELECT 1")
    repo.create_query_run("conn1", "SELECT 2", result={"columns": [], "rows": []})
    repo.create_query_run("conn2", "SELECT 3")
    assert len(repo.list_query_runs(50, 0)) == 3
    assert len(repo.list_query_runs(50, 0, connection_id="conn1")) == 2
    assert len(repo.list_query_runs(50, 0, status="recorded")) == 2
    assert len(repo.list_query_runs(50, 0, connection_id="conn1", status="succeeded")) == 1


def test_get_and_delete():
    r = repo.create_query_run("conn1", "SELECT 1")
    assert repo.get_query_run(r["id"])["id"] == r["id"]
    assert repo.delete_query_run(r["id"]) is True
    assert repo.get_query_run(r["id"]) is None
    assert repo.delete_query_run(r["id"]) is False
