import pytest
from fastapi.testclient import TestClient
from app.main import app, verify_api_key
from app.database import init_db, get_db_connection


@pytest.fixture(autouse=True)
def _setup():
    init_db()
    with get_db_connection() as conn:
        conn.execute("DELETE FROM query_runs")
        conn.execute("DELETE FROM connections")
        conn.commit()
    app.dependency_overrides[verify_api_key] = lambda: True
    yield
    app.dependency_overrides.clear()
    with get_db_connection() as conn:
        conn.execute("DELETE FROM query_runs")
        conn.execute("DELETE FROM connections")
        conn.commit()


client = TestClient(app)


def _conn():
    return client.post("/api/v1/connections", json={
        "connection_ref": "pg-local", "name": "PG", "dialect": "postgresql",
        "environment": "local", "host": "localhost", "port": 5432, "database": "d",
        "auth_mode": "none",
    }).json()["data"]["id"]


def _env(b):
    assert set(b.keys()) == {"status", "data", "meta"} and b["status"] == "success"
    return b


def test_recorded_run_201():
    cid = _conn()
    r = client.post("/api/v1/query-runs", json={"connection_id": cid, "sql": "SELECT 1"})
    assert r.status_code == 201
    b = _env(r.json())
    assert b["data"]["status"] == "recorded" and b["data"]["result"] is None
    assert r.headers.get("X-Request-ID")


def test_succeeded_run():
    cid = _conn()
    r = client.post("/api/v1/query-runs", json={"connection_id": cid, "sql": "SELECT id",
        "result": {"columns": ["id"], "rows": [[1], [2]], "truncated": False}})
    d = r.json()["data"]
    assert d["status"] == "succeeded" and d["row_count"] == 2
    assert d["result"]["rows"] == [[1], [2]]


def test_failed_run():
    cid = _conn()
    r = client.post("/api/v1/query-runs", json={"connection_id": cid, "sql": "SELECT bad",
        "execution_error": "boom"})
    d = r.json()["data"]
    assert d["status"] == "failed" and d["execution_error"] == "boom"


def test_unknown_connection_400():
    r = client.post("/api/v1/query-runs", json={"connection_id": "nope", "sql": "SELECT 1"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "BAD_REQUEST"


def test_empty_sql_422():
    cid = _conn()
    r = client.post("/api/v1/query-runs", json={"connection_id": cid, "sql": ""})
    assert r.status_code == 422


def test_list_filter_and_meta():
    cid = _conn()
    client.post("/api/v1/query-runs", json={"connection_id": cid, "sql": "SELECT 1"})
    client.post("/api/v1/query-runs", json={"connection_id": cid, "sql": "SELECT 2",
        "execution_error": "x"})
    r = client.get("/api/v1/query-runs", params={"connection_id": cid, "status": "failed"})
    b = _env(r.json())
    assert len(b["data"]) == 1 and b["data"][0]["status"] == "failed"
    assert b["meta"]["pagination"]["count"] == 1


def test_get_and_delete_404():
    cid = _conn()
    rid = client.post("/api/v1/query-runs", json={"connection_id": cid, "sql": "SELECT 1"}).json()["data"]["id"]
    assert client.get(f"/api/v1/query-runs/{rid}").status_code == 200
    assert client.delete(f"/api/v1/query-runs/{rid}").status_code == 200
    assert client.get(f"/api/v1/query-runs/{rid}").status_code == 404
    assert client.delete(f"/api/v1/query-runs/{rid}").status_code == 404


def test_requires_api_key():
    app.dependency_overrides.clear()
    assert client.get("/api/v1/query-runs").status_code == 403
