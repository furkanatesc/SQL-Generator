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
        conn.execute("DELETE FROM organizations WHERE slug != 'default'")
        conn.commit()
    app.dependency_overrides[verify_api_key] = lambda: True
    yield
    app.dependency_overrides.clear()
    with get_db_connection() as conn:
        conn.execute("DELETE FROM connections")
        conn.execute("DELETE FROM workspaces")
        conn.execute("DELETE FROM organizations WHERE slug != 'default'")
        conn.commit()


client = TestClient(app)


def _envelope(body):
    assert set(body.keys()) == {"status", "data", "meta"}
    assert body["status"] == "success"
    return body


def test_create_returns_201_canonical_envelope():
    r = client.post("/api/v1/workspaces", json={"name": "Alpha"})
    assert r.status_code == 201
    b = _envelope(r.json())
    assert b["data"]["name"] == "Alpha"
    assert b["data"]["slug"] == "alpha"
    assert b["data"]["id"]
    assert r.headers.get("X-Request-ID")


def test_create_with_explicit_slug_and_description():
    r = client.post("/api/v1/workspaces",
                    json={"name": "Beta", "slug": "beta-team", "description": "d"})
    b = _envelope(r.json())
    assert b["data"]["slug"] == "beta-team" and b["data"]["description"] == "d"


def test_duplicate_slug_returns_409_conflict():
    client.post("/api/v1/workspaces", json={"name": "Alpha"})
    r = client.post("/api/v1/workspaces", json={"name": "Alpha"})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "CONFLICT"


def test_invalid_body_returns_422():
    r = client.post("/api/v1/workspaces", json={"name": ""})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_get_missing_returns_404():
    r = client.get("/api/v1/workspaces/nope")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "NOT_FOUND"


def test_list_paginated_meta():
    for i in range(3):
        client.post("/api/v1/workspaces", json={"name": f"W{i}"})
    r = client.get("/api/v1/workspaces", params={"limit": 2, "offset": 0})
    assert r.status_code == 200
    b = _envelope(r.json())
    assert isinstance(b["data"], list) and len(b["data"]) == 2
    assert b["meta"]["pagination"] == {"limit": 2, "offset": 0, "count": 2}


def test_get_update_delete_roundtrip():
    created = client.post("/api/v1/workspaces", json={"name": "Alpha"}).json()["data"]
    wid = created["id"]
    got = client.get(f"/api/v1/workspaces/{wid}")
    assert got.status_code == 200 and got.json()["data"]["id"] == wid
    patched = client.patch(f"/api/v1/workspaces/{wid}", json={"name": "Alpha X"})
    assert patched.status_code == 200 and patched.json()["data"]["name"] == "Alpha X"
    deleted = client.delete(f"/api/v1/workspaces/{wid}")
    assert deleted.status_code == 200 and deleted.json()["data"]["id"] == wid
    assert client.get(f"/api/v1/workspaces/{wid}").status_code == 404


def test_patch_empty_body_returns_422():
    created = client.post("/api/v1/workspaces", json={"name": "Alpha"}).json()["data"]
    r = client.patch(f"/api/v1/workspaces/{created['id']}", json={})
    assert r.status_code == 422


def test_requires_api_key():
    app.dependency_overrides.clear()  # drop the auth override for this check
    r = client.get("/api/v1/workspaces")
    assert r.status_code == 403


def _org(name):
    r = client.post("/api/v1/organizations", json={"name": name})
    assert r.status_code == 201
    return r.json()["data"]["id"]


def _default_org_id():
    from app.organization_repository import get_default_organization
    return get_default_organization()["id"]


def test_create_without_org_uses_default_org():
    r = client.post("/api/v1/workspaces", json={"name": "Alpha"})
    assert r.status_code == 201
    assert r.json()["data"]["organization_id"] == _default_org_id()


def test_create_with_unknown_org_400():
    r = client.post("/api/v1/workspaces",
                    json={"name": "Alpha", "organization_id": "nope"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "BAD_REQUEST"
    assert r.json()["error"]["message"] == "organization_id mevcut değil"


def test_same_slug_in_two_orgs_ok_same_org_409():
    o1, o2 = _org("One"), _org("Two")
    body = {"name": "Alpha", "slug": "alpha"}
    assert client.post("/api/v1/workspaces", json={**body, "organization_id": o1}).status_code == 201
    r2 = client.post("/api/v1/workspaces", json={**body, "organization_id": o2})
    assert r2.status_code == 201 and r2.json()["data"]["organization_id"] == o2
    assert client.post("/api/v1/workspaces", json={**body, "organization_id": o1}).status_code == 409


def test_list_filter_by_organization():
    o1 = _org("One")
    client.post("/api/v1/workspaces", json={"name": "A"})
    b = client.post("/api/v1/workspaces", json={"name": "B", "organization_id": o1}).json()["data"]
    r = client.get("/api/v1/workspaces", params={"organization_id": o1})
    assert [w["id"] for w in r.json()["data"]] == [b["id"]]
    assert len(client.get("/api/v1/workspaces").json()["data"]) == 2


def test_delete_workspace_with_connection_409():
    wid = client.post("/api/v1/workspaces", json={"name": "Alpha"}).json()["data"]["id"]
    c = client.post("/api/v1/connections", json=dict(
        connection_ref="pg-local", name="PG Local", dialect="postgresql",
        environment="local", host="localhost", port=5432, database="sqlgen",
        auth_mode="secret_ref", secret_ref={"provider": "env", "key": "PG_PASSWORD"},
        workspace_id=wid))
    assert c.status_code == 201
    r = client.delete(f"/api/v1/workspaces/{wid}")
    assert r.status_code == 409
    assert client.get(f"/api/v1/workspaces/{wid}").status_code == 200


def test_list_workspaces_unknown_organization_is_empty():
    r = client.get("/api/v1/workspaces", params={"organization_id": "nope"})
    assert r.status_code == 200
    assert r.json()["data"] == []
