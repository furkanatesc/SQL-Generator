import pytest
from fastapi.testclient import TestClient
from app.main import app, verify_api_key
from app.database import init_db, get_db_connection


@pytest.fixture(autouse=True)
def _setup():
    init_db()
    with get_db_connection() as conn:
        conn.execute("DELETE FROM api_keys")
        conn.commit()
    app.dependency_overrides[verify_api_key] = lambda: True
    yield
    app.dependency_overrides.clear()
    with get_db_connection() as conn:
        conn.execute("DELETE FROM api_keys")
        conn.commit()


client = TestClient(app)


def _env(b):
    assert set(b.keys()) == {"status", "data", "meta"} and b["status"] == "success"
    return b


def test_create_returns_raw_key_once_201():
    r = client.post("/api/v1/api-keys", json={"name": "ci"})
    assert r.status_code == 201
    b = _env(r.json())
    assert b["data"]["name"] == "ci"
    assert b["data"]["api_key"] and b["data"]["api_key"].startswith(b["data"]["key_prefix"])
    assert b["data"]["active"] is True
    assert r.headers.get("X-Request-ID")


def test_list_and_detail_never_expose_raw_or_hash():
    client.post("/api/v1/api-keys", json={"name": "ci"})
    lst = _env(client.get("/api/v1/api-keys").json())
    assert len(lst["data"]) == 1
    entry = lst["data"][0]
    assert "api_key" not in entry and "key_hash" not in entry
    detail = _env(client.get(f"/api/v1/api-keys/{entry['id']}").json())
    assert "api_key" not in detail["data"] and "key_hash" not in detail["data"]


def test_revoke_flips_active():
    kid = client.post("/api/v1/api-keys", json={"name": "ci"}).json()["data"]["id"]
    r = client.post(f"/api/v1/api-keys/{kid}/revoke")
    assert r.status_code == 200
    assert r.json()["data"]["active"] is False and r.json()["data"]["revoked_at"]


def test_get_and_revoke_missing_404():
    assert client.get("/api/v1/api-keys/nope").status_code == 404
    assert client.post("/api/v1/api-keys/nope/revoke").status_code == 404


def test_empty_name_422():
    assert client.post("/api/v1/api-keys", json={"name": ""}).status_code == 422


def test_requires_api_key():
    app.dependency_overrides.clear()
    assert client.get("/api/v1/api-keys").status_code == 403
