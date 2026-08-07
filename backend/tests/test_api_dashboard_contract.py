import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
HEADERS = {"X-API-Key": "sqlgen_secret_dev_key"}

_SAMPLE = {
    "version": "dashboard_v1",
    "window": {"created_after": None, "created_before": None, "dialect": None,
               "trace_count": 0, "truncated": False, "scan_cap": 10000,
               "bucket": "day", "timeseries_truncated": False},
    "metrics": {"version": "metrics_v1"},
    "timeseries": [], "top_errors": [],
    "feedback": {"total": 0, "by_verdict": {}, "by_category": {}},
    "recent_activity": [],
}


@pytest.fixture
def fake_dashboard(monkeypatch):
    def _install(payload=None):
        def _bd(*, trace_store, created_after=None, created_before=None, dialect=None,
                bucket="day", top_n=10, recent_limit=20, scan_cap=10000):
            return payload or _SAMPLE
        monkeypatch.setattr("app.api.dashboard_api.build_dashboard", _bd)
    return _install


def test_dashboard_200_success_envelope(fake_dashboard):
    fake_dashboard()
    r = client.get("/api/debug/dashboard", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["dashboard"]["version"] == "dashboard_v1"


def test_dashboard_passes_query_params(monkeypatch):
    seen = {}

    def _bd(*, trace_store, created_after=None, created_before=None, dialect=None,
            bucket="day", top_n=10, recent_limit=20, scan_cap=10000):
        seen.update(bucket=bucket, top_n=top_n, recent_limit=recent_limit, dialect=dialect)
        return _SAMPLE
    monkeypatch.setattr("app.api.dashboard_api.build_dashboard", _bd)
    r = client.get("/api/debug/dashboard?bucket=hour&top_n=3&recent_limit=5&dialect=postgres",
                   headers=HEADERS)
    assert r.status_code == 200
    assert seen == {"bucket": "hour", "top_n": 3, "recent_limit": 5, "dialect": "postgres"}


def test_dashboard_invalid_bucket_422_when_debug_enabled(fake_dashboard):
    fake_dashboard()
    r = client.get("/api/debug/dashboard?bucket=week", headers=HEADERS)
    assert r.status_code == 422


def test_dashboard_invalid_bucket_404_when_debug_disabled(fake_dashboard, monkeypatch):
    fake_dashboard()

    class _Off:
        debug_endpoints_enabled = False
    monkeypatch.setattr("app.api.dashboard_api.get_settings", lambda: _Off())
    r = client.get("/api/debug/dashboard?bucket=week", headers=HEADERS)
    assert r.status_code == 404


def test_dashboard_requires_api_key(fake_dashboard):
    fake_dashboard()
    assert client.get("/api/debug/dashboard").status_code == 403


def test_dashboard_404_when_debug_disabled(fake_dashboard, monkeypatch):
    fake_dashboard()

    class _Off:
        debug_endpoints_enabled = False
    monkeypatch.setattr("app.api.dashboard_api.get_settings", lambda: _Off())
    assert client.get("/api/debug/dashboard", headers=HEADERS).status_code == 404
