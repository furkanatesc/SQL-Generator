import pytest

from app.bundle_service import build_bundle, BundleJobNotFound


class _FakeStore:
    def __init__(self, records=None, raises=False):
        self._records = records or []
        self._raises = raises

    def list_traces(self, query):
        if self._raises:
            raise RuntimeError("store patladi")
        return [r for r in self._records if r["payload"].get("job_id") == query.job_id]


def _install(monkeypatch, *, job, replay_payload, debug_trace=None):
    monkeypatch.setattr("app.bundle_service.get_job", lambda jid: job)

    class _Replay:
        def to_payload(self):
            return replay_payload
    monkeypatch.setattr("app.bundle_service.replay_job",
                        lambda jid, *, pipeline, trace_store: _Replay())

    class _Adapter:
        def __init__(self, store):
            pass

        def list_traces(self, query):
            return [debug_trace] if debug_trace else []
    monkeypatch.setattr("app.bundle_service.DebugTraceAdapter", _Adapter)


def test_build_bundle_happy_path(monkeypatch):
    e2e = {"payload": {"job_id": "job-1", "version": "end_to_end_trace_v1",
                       "spans": [{"stage": "retrieval", "detail": {"candidates": [
                           {"object_id": "orders", "object_type": "table",
                            "schema_hash": "h1"}]}}]}}
    _install(monkeypatch,
             job={"id": "job-1", "status": "failed", "dialect": "postgres",
                  "error_code": "e", "natural_query": "x", "result_sql": None},
             replay_payload={"version": "query_replay_v1", "verdict": "identical",
                             "retrieval": {"observed_tables": ["orders"]}},
             debug_trace={"generated_sql": "SELECT 1", "sql_valid": False,
                          "attempts": [], "sql_validation_errors": []})
    store = _FakeStore(records=[e2e])
    out = build_bundle("job-1", trace_store=store, pipeline=object())
    assert out["job_id"] == "job-1"
    assert out["schema"]["selected_tables"] == ["orders"]
    assert out["sql"]["generated_sql"] == "SELECT 1"
    assert out["replay"]["verdict"] == "identical"


def test_build_bundle_raises_when_job_missing(monkeypatch):
    monkeypatch.setattr("app.bundle_service.get_job", lambda jid: None)
    with pytest.raises(BundleJobNotFound):
        build_bundle("nope", trace_store=_FakeStore(), pipeline=object())


def test_build_bundle_trace_missing_yields_null_trace(monkeypatch):
    _install(monkeypatch,
             job={"id": "job-1", "status": "failed", "dialect": "postgres",
                  "error_code": None, "natural_query": "x", "result_sql": None},
             replay_payload={"version": "query_replay_v1", "verdict": "baseline_unavailable"})
    out = build_bundle("job-1", trace_store=_FakeStore(records=[]), pipeline=object())
    assert out["trace"] is None
    assert out["sql"] is None
    assert out["meta"]["trace_contract_version"] is None


def test_build_bundle_store_error_propagates(monkeypatch):
    _install(monkeypatch,
             job={"id": "job-1", "dialect": "postgres"},
             replay_payload={"version": "query_replay_v1", "verdict": "identical"})
    with pytest.raises(RuntimeError):
        build_bundle("job-1", trace_store=_FakeStore(raises=True), pipeline=object())


def test_build_bundle_redacts_secrets_in_trace(monkeypatch):
    # end_to_end normalde secret-free; yine de redaksiyon ek guvence olmali.
    e2e = {"payload": {"job_id": "job-1", "version": "end_to_end_trace_v1",
                       "spans": [], "note": "api_key=sk-LEAKLEAKLEAK"}}
    _install(monkeypatch,
             job={"id": "job-1", "dialect": "postgres", "natural_query": "x"},
             replay_payload={"version": "query_replay_v1", "verdict": "identical"})
    out = build_bundle("job-1", trace_store=_FakeStore(records=[e2e]), pipeline=object())
    import json
    assert "sk-LEAKLEAKLEAK" not in json.dumps(out["trace"])
