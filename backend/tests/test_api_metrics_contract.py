import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
HEADERS = {"X-API-Key": "sqlgen_secret_dev_key"}

_SAMPLE = {
    "version": "metrics_v1",
    "window": {"created_after": None, "created_before": None, "dialect": None,
               "trace_count": 0, "truncated": False, "scan_cap": 10000},
    "outcome": {"total": 0, "terminal_status": {}, "success_rate": None},
    "errors": {"by_code": {}, "by_category": {}},
    "latency_ms": {"count": 0, "p50": None, "p95": None, "p99": None,
                   "min": None, "max": None, "mean": None},
    "stages": {"intent": {}, "retrieval": {}, "generation": {}, "security": {}, "validation": {}},
}


@pytest.fixture
def fake_metrics(monkeypatch):
    def _install(payload=None):
        def _cmw(*, trace_store, created_after=None, created_before=None,
                 dialect=None, scan_cap=10000):
            return payload or _SAMPLE
        monkeypatch.setattr("app.api.metrics_api.compute_metrics_for_window", _cmw)
    return _install


def test_metrics_returns_200_success_envelope(fake_metrics):
    fake_metrics()
    r = client.get("/api/debug/metrics", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["metrics"]["version"] == "metrics_v1"
    assert body["metrics"]["window"]["trace_count"] == 0


def test_metrics_passes_query_params(fake_metrics, monkeypatch):
    seen = {}

    def _cmw(*, trace_store, created_after=None, created_before=None, dialect=None, scan_cap=10000):
        seen.update(created_after=created_after, created_before=created_before, dialect=dialect)
        return _SAMPLE
    monkeypatch.setattr("app.api.metrics_api.compute_metrics_for_window", _cmw)
    r = client.get("/api/debug/metrics?created_after=2026-01-01&dialect=postgres", headers=HEADERS)
    assert r.status_code == 200
    assert seen == {"created_after": "2026-01-01", "created_before": None, "dialect": "postgres"}


def test_metrics_requires_api_key(fake_metrics):
    fake_metrics()
    r = client.get("/api/debug/metrics")
    assert r.status_code == 403


def test_metrics_returns_404_when_debug_disabled(fake_metrics, monkeypatch):
    fake_metrics()

    class _Off:
        debug_endpoints_enabled = False
    monkeypatch.setattr("app.api.metrics_api.get_settings", lambda: _Off())
    r = client.get("/api/debug/metrics", headers=HEADERS)
    assert r.status_code == 404
