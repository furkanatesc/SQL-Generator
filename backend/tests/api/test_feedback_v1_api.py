import pytest
from fastapi.testclient import TestClient
from app.main import app, verify_api_key
from app.database import init_db, get_db_connection


@pytest.fixture(autouse=True)
def _setup():
    init_db()
    with get_db_connection() as conn:
        conn.execute("DELETE FROM query_run_feedback")
        conn.execute("DELETE FROM query_runs")
        conn.execute("DELETE FROM connections")
        conn.commit()
    app.dependency_overrides[verify_api_key] = lambda: True
    yield
    app.dependency_overrides.clear()
    with get_db_connection() as conn:
        conn.execute("DELETE FROM query_run_feedback")
        conn.execute("DELETE FROM query_runs")
        conn.execute("DELETE FROM connections")
        conn.commit()


client = TestClient(app)


def _run():
    cid = client.post("/api/v1/connections", json={"connection_ref": "pg", "name": "P",
        "dialect": "postgresql", "environment": "local", "host": "h", "port": 5432,
        "database": "d", "auth_mode": "none"}).json()["data"]["id"]
    return client.post("/api/v1/query-runs", json={"connection_id": cid, "sql": "SELECT 1"}).json()["data"]["id"]


def _env(b):
    assert set(b.keys()) == {"status", "data", "meta"} and b["status"] == "success"
    return b


def test_create_incorrect_201():
    rid = _run()
    r = client.post("/api/v1/feedback", json={"query_run_id": rid, "verdict": "incorrect",
        "category": "wrong_join", "note": "bad"})
    assert r.status_code == 201
    b = _env(r.json())
    assert b["data"]["query_run_id"] == rid and b["data"]["verdict"] == "incorrect"
    assert r.headers.get("X-Request-ID")


def test_create_correct_201():
    rid = _run()
    r = client.post("/api/v1/feedback", json={"query_run_id": rid, "verdict": "correct"})
    assert r.status_code == 201 and r.json()["data"]["category"] is None


def test_unknown_run_400():
    r = client.post("/api/v1/feedback", json={"query_run_id": "nope", "verdict": "correct"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "BAD_REQUEST"


def test_invariant_correct_with_category_422():
    rid = _run()
    r = client.post("/api/v1/feedback", json={"query_run_id": rid, "verdict": "correct",
        "category": "wrong_join"})
    assert r.status_code == 422


def test_invariant_other_without_note_422():
    rid = _run()
    r = client.post("/api/v1/feedback", json={"query_run_id": rid, "verdict": "incorrect",
        "category": "other"})
    assert r.status_code == 422


def test_list_filter_and_meta():
    rid = _run()
    client.post("/api/v1/feedback", json={"query_run_id": rid, "verdict": "correct"})
    client.post("/api/v1/feedback", json={"query_run_id": rid, "verdict": "incorrect",
        "category": "wrong_table", "note": "n"})
    r = client.get("/api/v1/feedback", params={"query_run_id": rid, "verdict": "correct"})
    b = _env(r.json())
    assert len(b["data"]) == 1 and b["meta"]["pagination"]["count"] == 1


def test_get_and_delete_404():
    rid = _run()
    fid = client.post("/api/v1/feedback", json={"query_run_id": rid, "verdict": "correct"}).json()["data"]["id"]
    assert client.get(f"/api/v1/feedback/{fid}").status_code == 200
    assert client.delete(f"/api/v1/feedback/{fid}").status_code == 200
    assert client.get(f"/api/v1/feedback/{fid}").status_code == 404
    assert client.delete(f"/api/v1/feedback/{fid}").status_code == 404


def test_requires_api_key():
    app.dependency_overrides.clear()
    assert client.get("/api/v1/feedback").status_code == 403
