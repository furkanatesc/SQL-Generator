"""Replay endpoint contract testleri (Sprint 27.4 T6)."""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.replay import ReplayResult, ReplayVerdict, RetrievalDelta
from app.replay_service import ReplayJobNotFound

client = TestClient(app)
HEADERS = {"X-API-Key": "sqlgen_secret_dev_key"}


@pytest.fixture
def fake_replay(monkeypatch):
    def _install(result=None, raises=None):
        def _replay_job(job_id, *, pipeline, trace_store):
            if raises:
                raise raises
            return result or ReplayResult(
                job_id=job_id, verdict=ReplayVerdict.IDENTICAL,
                baseline_trace_id="trace_base",
                retrieval=RetrievalDelta(baseline_tables=("orders",),
                                         observed_tables=("orders",)))
        monkeypatch.setattr("app.api.debug_replay.replay_job", _replay_job)
        # Gercek pipeline'i (ve SchemaManager'i) testte kurmayalim.
        monkeypatch.setattr("app.api.debug_replay.get_replay_pipeline",
                            lambda: object())
    return _install


def test_replay_returns_200_success_envelope(fake_replay):
    fake_replay()
    r = client.post("/api/debug/jobs/job-1/replay", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["replay"]["job_id"] == "job-1"
    assert body["replay"]["verdict"] == "identical"
    assert body["replay"]["version"] == "query_replay_v1"
    # Sinirda enum degil plain string
    assert isinstance(body["replay"]["verdict"], str)


def test_replay_returns_404_when_job_missing(fake_replay):
    fake_replay(raises=ReplayJobNotFound("job-x"))
    r = client.post("/api/debug/jobs/job-x/replay", headers=HEADERS)
    assert r.status_code == 404
    assert r.json()["error"]["message"]


def test_replay_requires_api_key(fake_replay):
    fake_replay()
    r = client.post("/api/debug/jobs/job-1/replay")
    assert r.status_code == 403


def test_replay_returns_404_when_debug_endpoints_disabled(fake_replay, monkeypatch):
    fake_replay()

    class _Off:
        debug_endpoints_enabled = False

    monkeypatch.setattr("app.api.debug_replay.get_settings", lambda: _Off())
    r = client.post("/api/debug/jobs/job-1/replay", headers=HEADERS)
    assert r.status_code == 404


def test_replay_payload_exposes_all_dimensions(fake_replay):
    fake_replay()
    r = client.post("/api/debug/jobs/job-1/replay", headers=HEADERS)
    replay = r.json()["replay"]
    for key in ("retrieval", "validation", "security", "error_code",
                "notes", "baseline_trace_id"):
        assert key in replay
