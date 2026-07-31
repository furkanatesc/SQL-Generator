import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
HEADERS = {"X-API-Key": "sqlgen_secret_dev_key"}

_SAMPLE = {
    "version": "llm_usage_v1",
    "currency": "USD",
    "window": {"created_after": None, "created_before": None, "bucket": "day",
               "trace_count": 0, "generation_count": 0, "truncated": False,
               "scan_cap": 10000, "timeseries_truncated": False},
    "totals": {"request_count": 0, "prompt_tokens": 0, "completion_tokens": 0,
               "total_tokens": 0, "estimated_cost": 0.0, "unpriced_request_count": 0},
    "by_model": [], "by_provider": [],
    "latency_ms": {"count": 0, "p50": None, "p95": None, "p99": None},
    "finish_reasons": {}, "timeseries": [],
    "pricing": {"models_priced": [], "models_missing_price": []},
}


@pytest.fixture
def fake_usage(monkeypatch):
    def _install(payload=None):
        def _bu(*, trace_store, created_after=None, created_before=None,
                bucket="day", scan_cap=10000):
            return payload or _SAMPLE
        monkeypatch.setattr("app.api.llm_usage_api.build_llm_usage", _bu)
    return _install


def test_llm_usage_200_success_envelope(fake_usage):
    fake_usage()
    r = client.get("/api/debug/llm-usage", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["usage"]["version"] == "llm_usage_v1"


def test_llm_usage_passes_query_params(monkeypatch):
    seen = {}

    def _bu(*, trace_store, created_after=None, created_before=None, bucket="day", scan_cap=10000):
        seen.update(bucket=bucket, created_after=created_after, created_before=created_before)
        return _SAMPLE
    monkeypatch.setattr("app.api.llm_usage_api.build_llm_usage", _bu)
    r = client.get("/api/debug/llm-usage?bucket=hour&created_after=2026-08-01T00:00:00",
                   headers=HEADERS)
    assert r.status_code == 200
    assert seen == {"bucket": "hour", "created_after": "2026-08-01T00:00:00", "created_before": None}


def test_llm_usage_invalid_bucket_422(fake_usage):
    fake_usage()
    assert client.get("/api/debug/llm-usage?bucket=week", headers=HEADERS).status_code == 422


def test_llm_usage_requires_api_key(fake_usage):
    fake_usage()
    assert client.get("/api/debug/llm-usage").status_code == 403


def test_llm_usage_404_when_debug_disabled(fake_usage, monkeypatch):
    fake_usage()

    class _Off:
        debug_endpoints_enabled = False
    monkeypatch.setattr("app.api.llm_usage_api.get_settings", lambda: _Off())
    assert client.get("/api/debug/llm-usage", headers=HEADERS).status_code == 404
