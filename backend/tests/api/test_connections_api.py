import pytest
from fastapi.testclient import TestClient
from app.main import app, verify_api_key
from app.database import init_db, get_db_connection


@pytest.fixture(autouse=True)
def _setup():
    init_db()
    with get_db_connection() as conn:
        conn.execute("DELETE FROM connections")
        conn.execute("DELETE FROM workspaces")
        conn.commit()
    app.dependency_overrides[verify_api_key] = lambda: True
    yield
    app.dependency_overrides.clear()
    with get_db_connection() as conn:
        conn.execute("DELETE FROM connections")
        conn.execute("DELETE FROM workspaces")
        conn.commit()


client = TestClient(app)


def _payload(**over):
    base = dict(
        connection_ref="pg-local", name="PG Local", dialect="postgresql",
        environment="local", host="localhost", port=5432, database="sqlgen",
        auth_mode="secret_ref", secret_ref={"provider": "env", "key": "PG_PASSWORD"},
    )
    base.update(over)
    return base


def _env(body):
    assert set(body.keys()) == {"status", "data", "meta"}
    assert body["status"] == "success"
    return body


def test_create_201_canonical_and_no_raw_secret():
    r = client.post("/api/v1/connections", json=_payload())
    assert r.status_code == 201
    b = _env(r.json())
    assert b["data"]["connection_ref"] == "pg-local"
    assert b["data"]["endpoint"] == {"host": "localhost", "port": 5432, "database": "sqlgen"}
    assert b["data"]["secret_ref"] == {"provider": "env", "key": "PG_PASSWORD"}
    assert b["data"]["access_mode"] == "read_only"
    assert "secret_provider" not in b["data"] and "secret_key" not in b["data"]
    assert r.headers.get("X-Request-ID")


def test_duplicate_ref_409():
    client.post("/api/v1/connections", json=_payload())
    r = client.post("/api/v1/connections", json=_payload(name="Other"))
    assert r.status_code == 409 and r.json()["error"]["code"] == "CONFLICT"


def test_domain_invalid_raw_secret_422():
    r = client.post("/api/v1/connections",
                    json=_payload(secret_ref={"provider": "env", "key": "postgres://u:p@h/d"}))
    assert r.status_code == 422 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_bad_port_422():
    r = client.post("/api/v1/connections", json=_payload(port=99999))
    assert r.status_code == 422


def test_unknown_workspace_400():
    r = client.post("/api/v1/connections", json=_payload(workspace_id="does-not-exist"))
    assert r.status_code == 400 and r.json()["error"]["code"] == "BAD_REQUEST"


def test_workspace_link_and_filter():
    ws = client.post("/api/v1/workspaces", json={"name": "WS"}).json()["data"]["id"]
    client.post("/api/v1/connections", json=_payload(connection_ref="a", workspace_id=ws))
    client.post("/api/v1/connections", json=_payload(connection_ref="b"))
    r = client.get("/api/v1/connections", params={"workspace_id": ws})
    b = _env(r.json())
    assert len(b["data"]) == 1 and b["data"][0]["connection_ref"] == "a"
    assert b["meta"]["pagination"]["count"] == 1


def test_list_paginated_meta():
    for i in range(3):
        client.post("/api/v1/connections", json=_payload(connection_ref=f"c{i}"))
    r = client.get("/api/v1/connections", params={"limit": 2, "offset": 0})
    b = _env(r.json())
    assert len(b["data"]) == 2 and b["meta"]["pagination"] == {"limit": 2, "offset": 0, "count": 2}


def test_get_update_delete_roundtrip():
    cid = client.post("/api/v1/connections", json=_payload()).json()["data"]["id"]
    assert client.get(f"/api/v1/connections/{cid}").status_code == 200
    patched = client.patch(f"/api/v1/connections/{cid}", json={"name": "Renamed", "environment": "dev"})
    assert patched.status_code == 200
    assert patched.json()["data"]["name"] == "Renamed"
    assert patched.json()["data"]["environment"] == "dev"
    assert client.delete(f"/api/v1/connections/{cid}").status_code == 200
    assert client.get(f"/api/v1/connections/{cid}").status_code == 404


def test_patch_auth_mode_to_none_clears_secret():
    cid = client.post("/api/v1/connections", json=_payload()).json()["data"]["id"]
    r = client.patch(f"/api/v1/connections/{cid}", json={"auth_mode": "none"})
    assert r.status_code == 200
    assert r.json()["data"]["auth_mode"] == "none"
    assert r.json()["data"]["secret_ref"] is None


def test_patch_empty_body_422():
    cid = client.post("/api/v1/connections", json=_payload()).json()["data"]["id"]
    assert client.patch(f"/api/v1/connections/{cid}", json={}).status_code == 422


def test_requires_api_key():
    app.dependency_overrides.clear()
    assert client.get("/api/v1/connections").status_code == 403
