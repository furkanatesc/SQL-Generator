import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.bundle_service import BundleJobNotFound

client = TestClient(app)
HEADERS = {"X-API-Key": "sqlgen_secret_dev_key"}


@pytest.fixture
def fake_bundle(monkeypatch):
    def _install(payload=None, raises=None):
        def _build_bundle(job_id, *, trace_store, pipeline):
            if raises:
                raise raises
            return payload or {"version": "debug_bundle_v1", "job_id": job_id,
                               "job": {"status": "failed"}, "trace": None,
                               "sql": None, "replay": {"verdict": "identical"},
                               "schema": None, "meta": {"bundle_contract_version": "debug_bundle_v1"}}
        monkeypatch.setattr("app.api.debug_bundle_api.build_bundle", _build_bundle)
        monkeypatch.setattr("app.api.debug_bundle_api.get_bundle_pipeline",
                            lambda: object())
    return _install


def test_bundle_returns_200_success_envelope(fake_bundle):
    fake_bundle()
    r = client.get("/api/debug/jobs/job-1/bundle", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["bundle"]["job_id"] == "job-1"
    assert body["bundle"]["version"] == "debug_bundle_v1"


def test_bundle_returns_404_when_job_missing(fake_bundle):
    fake_bundle(raises=BundleJobNotFound("job-x"))
    r = client.get("/api/debug/jobs/job-x/bundle", headers=HEADERS)
    assert r.status_code == 404
    assert r.json()["error"]["message"]


def test_bundle_requires_api_key(fake_bundle):
    fake_bundle()
    r = client.get("/api/debug/jobs/job-1/bundle")
    assert r.status_code == 403


def test_bundle_returns_404_when_debug_disabled(fake_bundle, monkeypatch):
    fake_bundle()

    class _Off:
        debug_endpoints_enabled = False
    monkeypatch.setattr("app.api.debug_bundle_api.get_settings", lambda: _Off())
    r = client.get("/api/debug/jobs/job-1/bundle", headers=HEADERS)
    assert r.status_code == 404
