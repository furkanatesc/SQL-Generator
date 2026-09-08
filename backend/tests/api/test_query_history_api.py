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
        conn.execute("DELETE FROM workspaces")
        conn.commit()
    app.dependency_overrides[verify_api_key] = lambda: True
    yield
    app.dependency_overrides.clear()
    with get_db_connection() as conn:
        conn.execute("DELETE FROM query_runs")
        conn.execute("DELETE FROM connections")
        conn.execute("DELETE FROM workspaces")
        conn.commit()


client = TestClient(app)


def _conn(ref, ws=None):
    body = {"connection_ref": ref, "name": "PG", "dialect": "postgresql",
            "environment": "local", "host": "localhost", "port": 5432,
            "database": "d", "auth_mode": "none"}
    if ws is not None:
        body["workspace_id"] = ws
    return client.post("/api/v1/connections", json=body).json()["data"]["id"]


def _ws():
    return client.post("/api/v1/workspaces", json={"name": "WS"}).json()["data"]["id"]


def _run(cid, sql, execution_error=None):
    body = {"connection_id": cid, "sql": sql}
    if execution_error is not None:
        body["execution_error"] = execution_error
    client.post("/api/v1/query-runs", json=body)


def _env(b):
    assert set(b.keys()) == {"status", "data", "meta"} and b["status"] == "success"
    return b


def test_list_envelope_and_shape():
    cid = _conn("pg")
    _run(cid, "SELECT 1")
    r = client.get("/api/v1/query-history")
    assert r.status_code == 200 and r.headers.get("X-Request-ID")
    b = _env(r.json())
    assert len(b["data"]) == 1
    assert set(b["data"][0].keys()) == {"id", "connection_id", "workspace_id", "sql",
                                        "status", "row_count", "created_at"}
    assert b["meta"]["pagination"]["count"] == 1


def test_filter_by_workspace():
    ws = _ws()
    c1 = _conn("pg1", ws=ws)
    c2 = _conn("pg2")  # no workspace
    _run(c1, "SELECT 1")
    _run(c2, "SELECT 2")
    r = client.get("/api/v1/query-history", params={"workspace_id": ws})
    b = _env(r.json())
    assert len(b["data"]) == 1 and b["data"][0]["connection_id"] == c1
    assert b["data"][0]["workspace_id"] == ws


def test_filter_status_and_text():
    cid = _conn("pg")
    _run(cid, "SELECT a")
    _run(cid, "DELETE y", execution_error="boom")
    assert len(_env(client.get("/api/v1/query-history", params={"status": "failed"}).json())["data"]) == 1
    assert len(_env(client.get("/api/v1/query-history", params={"q": "SELECT"}).json())["data"]) == 1


def test_summary():
    cid = _conn("pg")
    _run(cid, "SELECT 1")
    _run(cid, "SELECT 2", execution_error="x")
    r = client.get("/api/v1/query-history/summary")
    b = _env(r.json())
    assert b["data"]["total"] == 2
    assert b["data"]["by_status"]["succeeded"] == 0  # recorded, not succeeded
    assert b["data"]["by_status"]["recorded"] == 1 and b["data"]["by_status"]["failed"] == 1


def test_unknown_filter_empty():
    r = client.get("/api/v1/query-history", params={"connection_id": "nope"})
    assert _env(r.json())["data"] == []


def test_requires_api_key():
    app.dependency_overrides.clear()
    assert client.get("/api/v1/query-history").status_code == 403
