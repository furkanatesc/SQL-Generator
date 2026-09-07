import pytest
from fastapi.testclient import TestClient
from app.main import app, verify_api_key
from app.database import init_db, get_db_connection


@pytest.fixture(autouse=True)
def _setup():
    init_db()
    with get_db_connection() as conn:
        conn.execute("DELETE FROM schema_syncs")
        conn.execute("DELETE FROM connections")
        conn.commit()
    app.dependency_overrides[verify_api_key] = lambda: True
    yield
    app.dependency_overrides.clear()
    with get_db_connection() as conn:
        conn.execute("DELETE FROM schema_syncs")
        conn.execute("DELETE FROM connections")
        conn.commit()


client = TestClient(app)


def _conn():
    return client.post("/api/v1/connections", json={
        "connection_ref": "pg-local", "name": "PG", "dialect": "postgresql",
        "environment": "local", "host": "localhost", "port": 5432, "database": "d",
        "auth_mode": "none",
    }).json()["data"]["id"]


def _schema(*cols):
    return {"tables": {"users": {"columns": [{"name": c, "type": "int"} for c in cols],
                                 "foreign_keys": []}}}


def _env(b):
    assert set(b.keys()) == {"status", "data", "meta"} and b["status"] == "success"
    return b


def test_create_201_first_sync_drifted():
    cid = _conn()
    r = client.post("/api/v1/schema-syncs", json={"connection_id": cid, "structure": _schema("id")})
    assert r.status_code == 201
    b = _env(r.json())
    assert b["data"]["connection_id"] == cid
    assert b["data"]["drifted"] is True and b["data"]["previous_signature"] is None
    assert b["data"]["signature"]
    assert b["data"]["structure"]["tables"]["users"]
    assert r.headers.get("X-Request-ID")


def test_second_changed_sync_reports_drift():
    cid = _conn()
    client.post("/api/v1/schema-syncs", json={"connection_id": cid, "structure": _schema("id")})
    r = client.post("/api/v1/schema-syncs", json={"connection_id": cid, "structure": _schema("id", "email")})
    d = r.json()["data"]
    assert d["drifted"] is True
    assert {"table": "users", "column": "email"} in d["drift"]["added_columns"]


def test_unknown_connection_400():
    r = client.post("/api/v1/schema-syncs", json={"connection_id": "nope", "structure": _schema("id")})
    assert r.status_code == 400 and r.json()["error"]["code"] == "BAD_REQUEST"


def test_malformed_schema_422():
    cid = _conn()
    r = client.post("/api/v1/schema-syncs", json={"connection_id": cid, "structure": {"x": 1}})
    assert r.status_code == 422


def test_list_filter_and_meta():
    cid = _conn()
    for _ in range(2):
        client.post("/api/v1/schema-syncs", json={"connection_id": cid, "structure": _schema("id")})
    r = client.get("/api/v1/schema-syncs", params={"connection_id": cid, "limit": 1, "offset": 0})
    b = _env(r.json())
    assert len(b["data"]) == 1 and b["meta"]["pagination"] == {"limit": 1, "offset": 0, "count": 1}


def test_get_and_delete_404():
    cid = _conn()
    sid = client.post("/api/v1/schema-syncs", json={"connection_id": cid, "structure": _schema("id")}).json()["data"]["id"]
    assert client.get(f"/api/v1/schema-syncs/{sid}").status_code == 200
    assert client.delete(f"/api/v1/schema-syncs/{sid}").status_code == 200
    assert client.get(f"/api/v1/schema-syncs/{sid}").status_code == 404
    assert client.delete(f"/api/v1/schema-syncs/{sid}").status_code == 404


def test_requires_api_key():
    app.dependency_overrides.clear()
    assert client.get("/api/v1/schema-syncs").status_code == 403
