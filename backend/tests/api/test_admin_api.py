import pytest
from fastapi.testclient import TestClient
from app.main import app, verify_api_key
from app.database import init_db, get_db_connection


@pytest.fixture(autouse=True)
def _setup():
    init_db()
    with get_db_connection() as conn:
        conn.execute("DELETE FROM workspaces")
        conn.commit()
    app.dependency_overrides[verify_api_key] = lambda: True
    yield
    app.dependency_overrides.clear()
    with get_db_connection() as conn:
        conn.execute("DELETE FROM workspaces")
        conn.commit()


client = TestClient(app)


def _env(b):
    assert set(b.keys()) == {"status", "data", "meta"} and b["status"] == "success"
    return b


def test_overview_envelope_and_counts():
    client.post("/api/v1/workspaces", json={"name": "W1"})
    client.post("/api/v1/workspaces", json={"name": "W2"})
    r = client.get("/api/v1/admin/overview")
    assert r.status_code == 200 and r.headers.get("X-Request-ID")
    b = _env(r.json())
    assert b["data"]["environment"]
    assert "debug_endpoints_enabled" in b["data"]
    assert b["data"]["resources"]["workspaces"] == 2
    assert set(b["data"]["resources"].keys()) == {"workspaces", "connections",
        "schema_syncs", "query_runs", "query_run_feedback"}


def test_config_diagnostics():
    r = client.get("/api/v1/admin/config")
    assert r.status_code == 200
    b = _env(r.json())
    for k in ("environment", "debug_endpoints_enabled", "cors_origins_count",
              "upload_dir_configured", "api_key_configured",
              "startup_warnings_count", "startup_critical_warnings_count"):
        assert k in b["data"]


def test_requires_api_key():
    app.dependency_overrides.clear()
    assert client.get("/api/v1/admin/overview").status_code == 403
