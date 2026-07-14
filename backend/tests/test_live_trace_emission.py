from unittest.mock import MagicMock
from app.llm.fake_provider import DeterministicFakeLLMProvider
from app.sql_pipeline import SQLGenerationPipeline
from app.trace.models import TraceRecord


class RecordingStore:
    def __init__(self):
        self.records = []
        self.legacy = []

    def save(self, trace):
        self.records.append(trace)

    def save_legacy(self, trace):
        self.legacy.append(trace)


def _pipeline(store):
    pipeline = SQLGenerationPipeline(
        schema_manager=MagicMock(),
        llm_provider=DeterministicFakeLLMProvider(sql="SELECT 1"),
        trace_store=store)
    pipeline.schema_pruner = MagicMock()
    pipeline.schema_pruner.prune_schema.return_value = {
        "tables": {"users": {"columns": [{"name": "id", "type": "int"}]}},
        "estimated_tokens": 10}
    return pipeline


def _e2e_records(store):
    return [r for r in store.records
            if isinstance(r, TraceRecord) and r.trace_type == "end_to_end"]


def test_dual_emit_legacy_plus_end_to_end():
    store = RecordingStore()
    _pipeline(store).run_pipeline(job_id="j1", natural_query="kaç kullanıcı",
                                  dialect="postgres", request_id="req_x")
    assert len(store.legacy) == 1
    e2e = _e2e_records(store)
    assert len(e2e) == 1
    rec = e2e[0]
    assert rec.request_id == "req_x" and rec.job_id == "j1"
    payload = rec.payload
    assert len(payload["spans"]) == 7
    assert payload["terminal_status"] == "completed"
    by_stage = {s["stage"]: s for s in payload["spans"]}
    assert by_stage["execution"]["status"] == "skipped"
    assert by_stage["generation"]["status"] == "ok"
    assert isinstance(payload["total_duration_ms"], int)


def test_early_input_error_emits_failed_at_intent():
    store = RecordingStore()
    _pipeline(store).run_pipeline(job_id="j2", dialect="postgres",
                                  request_id="req_y")  # ne excel ne query
    rec = _e2e_records(store)[0]
    assert rec.payload["terminal_status"] == "failed"
    assert rec.payload["terminal_stage"] == "intent"
    by_stage = {s["stage"]: s for s in rec.payload["spans"]}
    assert by_stage["retrieval"]["status"] == "skipped"


def test_emission_failure_does_not_change_pipeline_result(monkeypatch):
    store = RecordingStore()
    pipeline = _pipeline(store)
    import app.sql_pipeline as sp

    def boom(**kwargs):
        raise RuntimeError("assembly exploded")

    monkeypatch.setattr(sp, "assemble_live_end_to_end_trace", boom)
    res = pipeline.run_pipeline(job_id="j3", natural_query="kaç kullanıcı",
                                dialect="postgres")
    assert res["success"] is True  # e2e patlasa da sonuç değişmez
    assert len(store.legacy) == 1  # legacy kayıt yine atıldı


def test_no_raw_sql_in_e2e_payload():
    store = RecordingStore()
    _pipeline(store).run_pipeline(job_id="j4", natural_query="kaç kullanıcı",
                                  dialect="postgres")
    import json
    text = json.dumps(_e2e_records(store)[0].payload)
    assert "SELECT 1" not in text  # yalnız sha256 taşınır
