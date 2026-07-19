"""live_trace_assembly kod listesi tutmaz, registry'den türetir (Sprint 27.2 T6)."""
from app.errors import ErrorCategory, ErrorCode, codes_for_category
from app.trace.end_to_end_trace import TraceSpanStatus, TraceStageKind
from app.trace.live_trace_assembly import assemble_live_end_to_end_trace

BASE = dict(
    trace_id="t" * 32, request_id="req_x", job_id="job_x", dialect="postgres",
    natural_query_redacted="q", total_duration_ms=5, stage_timings={},
    error_type=None, success=True, schema_selection_trace=None,
    pruned_tables=[], prompt_sha256=None, prompt_char_count=None,
    attempts_redacted=[], last_generated_sql_redacted=None,
)


def _span(trace, stage):
    return next(s for s in trace.spans if s.stage is stage)


def test_input_error_types_are_derived_from_the_registry():
    from app.trace import live_trace_assembly as m
    assert set(m._INPUT_ERROR_TYPES) == set(codes_for_category(ErrorCategory.INPUT))


def test_retrieval_error_types_are_derived_from_the_registry():
    from app.trace import live_trace_assembly as m
    assert set(m._RETRIEVAL_ERROR_TYPES) == set(
        codes_for_category(ErrorCategory.RETRIEVAL))


def test_renamed_retrieval_code_produces_an_error_span():
    t = assemble_live_end_to_end_trace(**{
        **BASE, "error_type": ErrorCode.SCHEMA_PRUNING_FAILED, "success": False,
        "stage_timings": {"retrieval": 7}})
    span = _span(t, TraceStageKind.RETRIEVAL)
    assert span.status is TraceSpanStatus.ERROR
    assert span.attributes["reason_code"] == "schema_pruning_failed"
    assert span.duration_ms == 7


def test_generation_error_now_produces_a_generation_error_span():
    """v1'in eksiği: sql_generation_failed ve llm_api_error hiçbir sette yoktu,
    yani bir üretim hatası bu dallardan reason_code'lu ERROR span üretmiyordu.
    Kategori modeli bunu kendiliğinden kapatır."""
    from app.trace import live_trace_assembly as m
    generation_codes = codes_for_category(ErrorCategory.GENERATION)
    assert ErrorCode.SQL_GENERATION_EXHAUSTED in generation_codes
    assert ErrorCode.LLM_API_ERROR in generation_codes
    # GENERATION kodları INPUT/RETRIEVAL setlerine SIZMAZ:
    assert not (generation_codes & set(m._INPUT_ERROR_TYPES))
    assert not (generation_codes & set(m._RETRIEVAL_ERROR_TYPES))


def test_security_stages_set_is_still_stages_not_codes():
    """_SECURITY_STAGES bir STAGE setidir (kod değil) ve yerinde kalır —
    spec §3.3'ün kategori/stage ayrımı gereği."""
    from app.trace import live_trace_assembly as m
    assert m._SECURITY_STAGES == frozenset({"sql_guardrail", "sql_sandbox_safety"})
    for stage in m._SECURITY_STAGES:
        assert stage not in {c.value for c in ErrorCode}


def test_assembly_accepts_plain_strings_too():
    # error_type düz string gelirse de çalışmalı (StrEnum eşitliği).
    t = assemble_live_end_to_end_trace(**{
        **BASE, "error_type": "input_error", "success": False})
    assert _span(t, TraceStageKind.INTENT).status is TraceSpanStatus.ERROR
