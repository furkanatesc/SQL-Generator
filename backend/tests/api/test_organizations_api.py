import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from app.main import app, verify_api_key
from app.database import init_db, get_db_connection


def _clean():
    with get_db_connection() as conn:
        conn.execute("DELETE FROM workspaces")
        conn.execute("DELETE FROM organizations WHERE slug != 'default'")
        conn.commit()


@pytest.fixture(autouse=True)
def _setup():
    init_db()
    _clean()
    app.dependency_overrides[verify_api_key] = lambda: True
    yield
    app.dependency_overrides.clear()
    _clean()


client = TestClient(app)


def _envelope(body):
    assert set(body.keys()) == {"status", "data", "meta"}
    assert body["status"] == "success"
    return body


def test_create_returns_201_envelope():
    r = client.post("/api/v1/organizations", json={"name": "Acme Corp"})
    assert r.status_code == 201
    b = _envelope(r.json())
    assert b["data"]["slug"] == "acme-corp" and b["data"]["id"]
    assert r.headers.get("X-Request-ID")


def test_duplicate_slug_409():
    client.post("/api/v1/organizations", json={"name": "Acme"})
    r = client.post("/api/v1/organizations", json={"name": "Acme"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "CONFLICT"


def test_invalid_body_422():
    r = client.post("/api/v1/organizations", json={"name": ""})
    assert r.status_code == 422


def test_list_pagination_meta():
    for n in ("A", "B", "C"):
        client.post("/api/v1/organizations", json={"name": n})
    r = client.get("/api/v1/organizations?limit=2&offset=1")
    b = _envelope(r.json())
    assert len(b["data"]) == 2
    assert b["meta"]["pagination"] == {"limit": 2, "offset": 1, "count": 2}
    assert client.get("/api/v1/organizations?limit=0").status_code == 422


def test_get_patch_delete_missing_404():
    assert client.get("/api/v1/organizations/nope").status_code == 404
    assert client.patch("/api/v1/organizations/nope", json={"name": "x"}).status_code == 404
    assert client.delete("/api/v1/organizations/nope").status_code == 404


def test_get_patch_delete_roundtrip():
    oid = client.post("/api/v1/organizations", json={"name": "Acme"}).json()["data"]["id"]
    assert client.get(f"/api/v1/organizations/{oid}").json()["data"]["name"] == "Acme"
    r = client.patch(f"/api/v1/organizations/{oid}", json={"name": "New"})
    assert r.json()["data"]["name"] == "New"
    assert client.patch(f"/api/v1/organizations/{oid}", json={}).status_code == 422
    assert client.delete(f"/api/v1/organizations/{oid}").status_code == 200
    assert client.get(f"/api/v1/organizations/{oid}").status_code == 404


def test_delete_default_409():
    items = client.get("/api/v1/organizations").json()["data"]
    d = next(o for o in items if o["slug"] == "default")
    r = client.delete(f"/api/v1/organizations/{d['id']}")
    assert r.status_code == 409


def test_delete_org_with_workspace_409():
    oid = client.post("/api/v1/organizations", json={"name": "Acme"}).json()["data"]["id"]
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO workspaces (id, organization_id, name, slug, description, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (uuid.uuid4().hex, oid, "W", "w", None, "t", "t"),
        )
        conn.commit()
    assert client.delete(f"/api/v1/organizations/{oid}").status_code == 409


def test_parallel_same_slug_creates_one_winner():
    def post():
        return client.post("/api/v1/organizations", json={"name": "Race", "slug": "race"}).status_code

    with ThreadPoolExecutor(max_workers=12) as pool:
        codes = [f.result() for f in [pool.submit(post) for _ in range(12)]]
    assert sorted(codes) == [201] + [409] * 11


def test_admin_overview_counts_organizations():
    r = client.get("/api/v1/admin/overview")
    assert r.json()["data"]["resources"]["organizations"] >= 1
