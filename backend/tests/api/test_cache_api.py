import pytest
from fastapi.testclient import TestClient

import app.api.cache_api as api
from app.main import app

client = TestClient(app)
HEADERS = {"X-API-Key": "sqlgen_secret_dev_key"}


@pytest.fixture(autouse=True)
def fake_store(monkeypatch):
    state = {"entries": 3, "total_hits": 7}
    monkeypatch.setattr(api, "cache_stats", lambda: {"entries": state["entries"], "total_hits": state["total_hits"]})
    monkeypatch.setattr(api, "clear_cache", lambda: state["entries"])
    return state


def test_stats_returns_envelope():
    r = client.get("/api/debug/cache/stats", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["entries"] == 3 and body["total_hits"] == 7


def test_clear_returns_deleted_count():
    r = client.post("/api/debug/cache/clear", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["deleted"] == 3


def test_stats_requires_api_key():
    assert client.get("/api/debug/cache/stats").status_code == 403


def test_stats_404_when_debug_disabled(monkeypatch):
    class _Off:
        debug_endpoints_enabled = False
    monkeypatch.setattr(api, "get_settings", lambda: _Off())
    assert client.get("/api/debug/cache/stats", headers=HEADERS).status_code == 404


def test_clear_404_when_debug_disabled(monkeypatch):
    class _Off:
        debug_endpoints_enabled = False
    monkeypatch.setattr(api, "get_settings", lambda: _Off())
    assert client.post("/api/debug/cache/clear", headers=HEADERS).status_code == 404
