"""replay_service adaptor testleri (Sprint 27.4 T5).

LLM'e HIC gidilmez; pipeline ve trace store fake'lenir.
"""
import pytest

from app.replay import ReplayVerdict
from app.replay_service import ReplayJobNotFound, _split_issue_types, replay_job
from app.sql_pipeline import ValidationOutcome
from app.trace.models import TraceRecord


def _e2e_payload(tables=("orders",), valid=True, denied=()):
    return {
        "version": "end_to_end_trace_v1",
        "trace_id": "trace_base",
        "request_id": "req_1",
        "terminal_status": "completed",
        "terminal_stage": "execution",
        "job_id": "job-1",
        "dialect": "postgres",
        "nl_query_sha256": "abc",
        "total_duration_ms": 5,
        "spans": [
            {"stage": "retrieval", "status": "ok", "duration_ms": 1,
             "detail_kind": "RetrievalSpanDetail",
             "detail": {"k_requested": None, "k_returned": len(tables),
                        "candidates": [
                            {"object_id": t, "object_type": "table", "score": 0.0,
                             "rank": i, "schema_hash": None}
                            for i, t in enumerate(tables)],
                        "retrieval_version": "v"},
             "attributes": {}},
            {"stage": "validation", "status": "ok", "duration_ms": 1,
             "detail_kind": "ValidationSpanDetail",
             "detail": {"valid": valid, "sql_sha256": "x", "issues": []},
             "attributes": {}},
            {"stage": "security", "status": "ok", "duration_ms": 1,
             "detail_kind": "SecuritySpanDetail",
             "detail": {"checks": [
                 {"category": c, "outcome": "denied", "severity": "error",
                  "reason_code": c, "audit_entry_hash": None} for c in denied
             ] or [{"category": "sql_guardrail", "outcome": "allowed",
                    "severity": "info", "reason_code": None,
                    "audit_entry_hash": None}]},
             "attributes": {}},
        ],
    }


class _FakeStore:
    def __init__(self, records):
        self._records = records
        self.saved = []

    def list_traces(self, query=None):
        return list(self._records)

    def save(self, trace):
        self.saved.append(trace)
        return trace


class _FakePipeline:
    def __init__(self, *, tables=("orders",), retrieval_error=None,
                 validation_valid=True, validation_errors=None):
        self._tables = tables
        self._retrieval_error = retrieval_error
        self._validation_valid = validation_valid
        self._validation_errors = validation_errors or []
        self.validate_calls = []
        self.intent_calls = []

    def _stage_intent(self, *, excel_file_path, natural_query, log_callback):
        self.intent_calls.append(
            {"excel_file_path": excel_file_path, "natural_query": natural_query})
        if not natural_query and not excel_file_path:
            return None, {"message": "bos", "error_type": "input_error"}, 0
        return {"natural_query": natural_query or "excel"}, None, 0

    def _stage_retrieval(self, *, aqr, natural_query, dialect, log_callback):
        if self._retrieval_error:
            return ({}, None, None,
                    {"message": "bozuk", "error_type": self._retrieval_error,
                     "pruned_schema_for_trace": {}, "pruned_tables": []}, 0)
        pruned = {"tables": {t: {"columns": []} for t in self._tables}}
        trace = {"selected_tables": list(self._tables)}
        return pruned, "ctx", trace, None, 0

    def validate_sql(self, sql, pruned_schema, dialect, log_callback=None):
        self.validate_calls.append(sql)
        return ValidationOutcome(
            sql=sql, valid=self._validation_valid,
            retry_disposition="ok" if self._validation_valid else "retry",
            validation_errors=list(self._validation_errors),
            error_message=None if self._validation_valid else "bozuk")


@pytest.fixture
def job_row(monkeypatch):
    row = {
        "id": "job-1", "status": "completed", "file_path": None,
        "natural_query": "en cok satan urunler", "previous_sql": None,
        "result_sql": "SELECT 1", "error_message": None, "error_code": None,
        "dialect": "postgres", "created_at": "2026-07-24T00:00:00",
        "updated_at": "2026-07-24T00:00:00",
    }
    monkeypatch.setattr("app.replay_service.get_job",
                        lambda job_id: row if job_id == "job-1" else None)
    return row


def test_missing_job_raises(job_row):
    with pytest.raises(ReplayJobNotFound):
        replay_job("yok", pipeline=_FakePipeline(), trace_store=_FakeStore([]))


def test_identical_when_nothing_changed(job_row):
    store = _FakeStore([TraceRecord(trace_type="end_to_end",
                                    payload=_e2e_payload(), job_id="job-1")])
    result = replay_job("job-1", pipeline=_FakePipeline(), trace_store=store)
    assert result.verdict == ReplayVerdict.IDENTICAL
    assert result.baseline_trace_id == "trace_base"


def test_baseline_unavailable_when_no_end_to_end_trace(job_row):
    result = replay_job("job-1", pipeline=_FakePipeline(),
                        trace_store=_FakeStore([]))
    assert result.verdict == ReplayVerdict.BASELINE_UNAVAILABLE


def test_retrieval_drift_detected(job_row):
    store = _FakeStore([TraceRecord(trace_type="end_to_end",
                                    payload=_e2e_payload(tables=("orders",)),
                                    job_id="job-1")])
    result = replay_job("job-1",
                        pipeline=_FakePipeline(tables=("orders", "customers")),
                        trace_store=store)
    assert result.verdict == ReplayVerdict.RETRIEVAL_DRIFT
    assert result.retrieval.added == ("customers",)


def test_replay_failed_when_retrieval_errors_today(job_row):
    store = _FakeStore([TraceRecord(trace_type="end_to_end",
                                    payload=_e2e_payload(), job_id="job-1")])
    result = replay_job(
        "job-1",
        pipeline=_FakePipeline(retrieval_error="schema_pruning_failed"),
        trace_store=store)
    assert result.verdict == ReplayVerdict.REPLAY_FAILED
    assert result.error_code == "schema_pruning_failed"


def test_input_unavailable_when_excel_file_is_gone(monkeypatch):
    row = {
        "id": "job-2", "status": "completed", "file_path": "/yok/olan/dosya.xlsx",
        "natural_query": None, "previous_sql": None, "result_sql": "SELECT 1",
        "error_message": None, "error_code": None, "dialect": "postgres",
        "created_at": "x", "updated_at": "x",
    }
    monkeypatch.setattr("app.replay_service.get_job", lambda job_id: row)
    result = replay_job("job-2", pipeline=_FakePipeline(),
                        trace_store=_FakeStore([]))
    assert result.verdict == ReplayVerdict.INPUT_UNAVAILABLE


def test_validation_not_applicable_when_job_has_no_result_sql(monkeypatch):
    row = {
        "id": "job-3", "status": "failed", "file_path": None,
        "natural_query": "bir sorgu", "previous_sql": None, "result_sql": "",
        "error_message": "patladi", "error_code": "llm_api_error",
        "dialect": "postgres", "created_at": "x", "updated_at": "x",
    }
    monkeypatch.setattr("app.replay_service.get_job", lambda job_id: row)
    store = _FakeStore([TraceRecord(trace_type="end_to_end",
                                    payload=_e2e_payload(), job_id="job-3")])
    pipeline = _FakePipeline()
    result = replay_job("job-3", pipeline=pipeline, trace_store=store)
    assert result.validation.applicable is False
    assert pipeline.validate_calls == []   # bos SQL dogrulanmaz
    assert any("result_sql" in n for n in result.notes)


def test_replay_never_writes_anything(job_row):
    store = _FakeStore([TraceRecord(trace_type="end_to_end",
                                    payload=_e2e_payload(), job_id="job-1")])
    replay_job("job-1", pipeline=_FakePipeline(), trace_store=store)
    assert store.saved == []


def test_validation_regression_maps_error_type_axis(job_row):
    store = _FakeStore([TraceRecord(trace_type="end_to_end",
                                    payload=_e2e_payload(valid=True),
                                    job_id="job-1")])
    pipeline = _FakePipeline(
        validation_valid=False,
        validation_errors=[{"type": "missing_column",
                            "stage": "semantic_validation",
                            "message": "kolon yok"}])
    result = replay_job("job-1", pipeline=pipeline, trace_store=store)
    assert result.verdict == ReplayVerdict.VALIDATION_REGRESSION
    # uretim tarafinda eksen adi "type", trace tarafinda "category" idi
    assert result.validation.observed_issue_types == ("missing_column",)


def test_excel_branch_runs_when_both_inputs_present(monkeypatch):
    # Uretimde /api/files/upload hem file hem natural_query'yi ayni job'a
    # yazabilir; _stage_intent excel'i onceler. Adaptor da ayni yolu
    # kosmali — natural_query'yi atlayip excel_file_path'i None'a
    # dusurmemeli.
    row = {
        "id": "job-4", "status": "completed", "file_path": "/var/uploads/job-4.xlsx",
        "natural_query": "en cok satan urunler", "previous_sql": None,
        "result_sql": "SELECT 1", "error_message": None, "error_code": None,
        "dialect": "postgres", "created_at": "x", "updated_at": "x",
    }
    monkeypatch.setattr("app.replay_service.get_job", lambda job_id: row)
    monkeypatch.setattr("app.replay_service.os.path.exists", lambda p: True)

    store = _FakeStore([TraceRecord(trace_type="end_to_end",
                                    payload=_e2e_payload(), job_id="job-4")])
    pipeline = _FakePipeline()
    replay_job("job-4", pipeline=pipeline, trace_store=store)

    assert len(pipeline.intent_calls) == 1
    assert pipeline.intent_calls[0]["excel_file_path"] is not None
    assert pipeline.intent_calls[0]["excel_file_path"] == "/var/uploads/job-4.xlsx"
    assert pipeline.intent_calls[0]["natural_query"] == "en cok satan urunler"


def test_security_only_failure_does_not_lower_validation_valid(job_row):
    # live_trace_assembly.py:152-160 ile ayni eksen kurali: yalniz guvenlik
    # nedeniyle reddedilen SQL dogrulama ekseninde basarisiz SAYILMAZ.
    store = _FakeStore([TraceRecord(trace_type="end_to_end",
                                    payload=_e2e_payload(valid=True),
                                    job_id="job-1")])
    pipeline = _FakePipeline(
        validation_valid=False,
        validation_errors=[{"type": "unsafe_sandbox_rejected",
                            "stage": "sql_sandbox_safety",
                            "message": "guvensiz sorgu"}])
    result = replay_job("job-1", pipeline=pipeline, trace_store=store)
    assert result.validation.observed_valid is True
    assert result.security.observed_denied == ("unsafe_sandbox_rejected",)


def test_split_issue_types_uses_category_not_stage():
    # Sprint 27.4 merge-kapisi duzeltmesi: eksen KATEGORIDEN turetilir, stage'ten
    # degil. sql_parse_error stage="sql_guardrail" tasisa bile VALIDATION
    # kategorisindedir; unsafe_dml_keyword ise gercekten SECURITY'dir.
    errors = [
        {"type": "sql_parse_error", "stage": "sql_guardrail", "message": "bozuk"},
        {"type": "unsafe_dml_keyword", "stage": "sql_guardrail",
         "message": "guvensiz"},
    ]
    validation_types, security_types = _split_issue_types(errors)
    assert validation_types == ("sql_parse_error",)
    assert security_types == ("unsafe_dml_keyword",)


def test_split_issue_types_unknown_code_from_security_stage_goes_security():
    # Minor-1 (27.4 merge-kapisi): registry'de olmayan bir kod sql_guardrail/
    # sql_sandbox_safety asamasindan gelirse guvenlik eksenine dusmeli — bu,
    # baseline_extraction._belongs_to_security_axis'in ayni durumda GUVENLIKTE
    # TUTMA muhafazakarligiyla simetriktir.
    errors = [{"type": "unknown_new_denial", "stage": "sql_guardrail",
               "message": "kaydedilmemis yeni bir guvenlik reddi"}]
    validation_types, security_types = _split_issue_types(errors)
    assert validation_types == ()
    assert security_types == ("unknown_new_denial",)


def test_split_issue_types_unknown_code_from_non_security_stage_goes_validation():
    # Ayni bilinmeyen kod guvenlik-disi bir stage'den gelirse dogrulama
    # eksenine dusmeli.
    errors = [{"type": "unknown_semantic_issue", "stage": "semantic_validation",
               "message": "kaydedilmemis bir dogrulama sorunu"}]
    validation_types, security_types = _split_issue_types(errors)
    assert validation_types == ("unknown_semantic_issue",)
    assert security_types == ()


def test_unknown_security_code_symmetry_yields_identical_not_regression(job_row):
    # Minor-1 asil senaryo: biri registry'ye kaydetmeden yeni bir guvenlik
    # reddi ekler (ör. "unknown_new_denial", stage="sql_guardrail"). Baseline
    # bu bilinmeyen kodu guvenlik ekseninde TUTAR (_belongs_to_security_axis
    # muhafazakarligi). Bugun de AYNI kod, ayni stage'den, hicbir sey
    # degismemis olarak geldiginde eski (asimetrik) davranista bilinmeyen kod
    # dogrulama eksenine dusuyor, gozlemin validation_valid'i False'a
    # cekiyordu ve verdict yanlislikla VALIDATION_REGRESSION cikiyordu.
    # Fix sonrasi stage tiebreak sayesinde iki taraf da guvenlik eksenine
    # dustugu icin verdict IDENTICAL olmali.
    store = _FakeStore([TraceRecord(
        trace_type="end_to_end",
        payload=_e2e_payload(tables=("orders",), valid=True,
                             denied=("unknown_new_denial",)),
        job_id="job-1")])
    pipeline = _FakePipeline(
        tables=("orders",),
        validation_valid=False,
        validation_errors=[{"type": "unknown_new_denial",
                            "stage": "sql_guardrail",
                            "message": "kaydedilmemis yeni bir guvenlik reddi"}])
    result = replay_job("job-1", pipeline=pipeline, trace_store=store)
    assert result.verdict == ReplayVerdict.IDENTICAL
    assert result.security.observed_denied == ("unknown_new_denial",)
    assert result.security.baseline_denied == ("unknown_new_denial",)
    assert result.validation.observed_valid is True


def test_retry_recovered_parse_error_yields_identical_not_security_recovery(job_row):
    # ASIL SENARYO (Sprint 27.4 merge-kapisi bulgusu): LLM ilk denemede bozuk
    # SQL uretir -> guardrail sql_parse_error ile reddeder (stage=
    # "sql_guardrail", retryable) -> ikinci denemede temiz SELECT uretilir ->
    # job basariyla tamamlanir. Baseline'in SECURITY span'inde bu gecici
    # sql_parse_error "denied" olarak kalir (tum attempt'lerin birlesimi).
    # Bugun hicbir sey degismemisken (ayni tablolar, ayni gecerli SQL, guvenlik
    # ihlali YOK) verdict IDENTICAL olmali — SECURITY_RECOVERY DEGIL.
    store = _FakeStore([TraceRecord(
        trace_type="end_to_end",
        payload=_e2e_payload(tables=("orders",), valid=True,
                             denied=("sql_parse_error",)),
        job_id="job-1")])
    pipeline = _FakePipeline(tables=("orders",), validation_valid=True,
                             validation_errors=[])
    result = replay_job("job-1", pipeline=pipeline, trace_store=store)
    assert result.verdict == ReplayVerdict.IDENTICAL
    assert result.security.observed_denied == ()
    assert result.security.baseline_denied == ()
