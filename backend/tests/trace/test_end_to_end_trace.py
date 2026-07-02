import json
import sys

import pytest

from app.trace.end_to_end_trace import (
    END_TO_END_TRACE_CONTRACT_VERSION, EndToEndTraceError,
    TraceStageKind, TraceSpanStatus, TraceTerminalStatus,
    ExecutionSpanDetail, SecurityCheck, SecuritySpanDetail,
    TraceSpan, EndToEndTrace,
)

_V = END_TO_END_TRACE_CONTRACT_VERSION


def _ok_span(stage=TraceStageKind.EXECUTION):
    return TraceSpan(stage=stage, status=TraceSpanStatus.OK)


def _trace(**kw):
    base = dict(
        version=_V, trace_id="t1", request_id="r1",
        terminal_status=TraceTerminalStatus.COMPLETED,
        spans=(_ok_span(),), terminal_stage=TraceStageKind.EXECUTION,
    )
    base.update(kw)
    return EndToEndTrace(**base)


def test_happy_trace_is_frozen():
    t = _trace()
    assert t.version == _V
    with pytest.raises(Exception):
        t.trace_id = "x"


def test_version_mismatch_raises():
    with pytest.raises(EndToEndTraceError):
        _trace(version="wrong_v")


def test_empty_ids_raise():
    with pytest.raises(EndToEndTraceError):
        _trace(trace_id="")
    with pytest.raises(EndToEndTraceError):
        _trace(request_id="  ")


def test_duplicate_stage_raises():
    with pytest.raises(EndToEndTraceError):
        _trace(spans=(_ok_span(), _ok_span()))


def test_failed_terminal_requires_error_span():
    # terminal FAILED but the terminal_stage span is not ERROR -> invalid
    with pytest.raises(EndToEndTraceError):
        _trace(terminal_status=TraceTerminalStatus.FAILED,
               terminal_stage=TraceStageKind.EXECUTION,
               spans=(_ok_span(),))


def test_completed_with_error_span_raises():
    err = TraceSpan(stage=TraceStageKind.VALIDATION, status=TraceSpanStatus.ERROR)
    with pytest.raises(EndToEndTraceError):
        _trace(spans=(err,), terminal_stage=None)


def test_failed_terminal_with_matching_error_span_ok():
    err = TraceSpan(stage=TraceStageKind.VALIDATION, status=TraceSpanStatus.ERROR)
    t = _trace(terminal_status=TraceTerminalStatus.FAILED,
               terminal_stage=TraceStageKind.VALIDATION, spans=(err,))
    assert t.terminal_status == TraceTerminalStatus.FAILED


def test_attributes_must_be_str_values():
    with pytest.raises(EndToEndTraceError):
        TraceSpan(stage=TraceStageKind.PROMPT, status=TraceSpanStatus.OK,
                  attributes={"k": 123})  # non-str value


def test_to_payload_is_json_safe_and_secret_free():
    detail = ExecutionSpanDetail(
        execution_status="executed", dialect="postgresql",
        sql_sha256="a" * 64, row_count=3, truncated=False)
    sec = SecuritySpanDetail(checks=(
        SecurityCheck(category="read_only", outcome="allowed",
                      severity="info", reason_code="read_only_op",
                      audit_entry_hash="b" * 64),))
    spans = (
        TraceSpan(stage=TraceStageKind.SECURITY, status=TraceSpanStatus.OK,
                  duration_ms=1.0, detail=sec),
        TraceSpan(stage=TraceStageKind.EXECUTION, status=TraceSpanStatus.OK,
                  duration_ms=2.0, detail=detail, attributes={"adapter": "sqlite"}),
    )
    t = _trace(spans=spans, nl_query_sha256="c" * 64, dialect="postgresql",
               job_id="j1", total_duration_ms=3.0)
    payload = t.to_payload()
    dumped = json.dumps(payload)  # must not raise
    assert '"version": "end_to_end_trace_v1"' in dumped
    assert "a" * 64 in dumped              # sql_sha256 present
    assert "SELECT" not in dumped.upper()  # no raw sql
    assert payload["spans"][1]["detail"]["sql_sha256"] == "a" * 64
    assert payload["spans"][0]["detail"]["checks"][0]["audit_entry_hash"] == "b" * 64


def test_contract_module_does_not_load_drivers():
    # importing the pure contract must not pull app.evaluation or DB drivers.
    # Snapshot sys.modules before to avoid false positives from other tests
    # that may have already loaded drivers earlier in the suite.
    before = set(sys.modules)
    import app.trace.end_to_end_trace  # noqa: F401
    newly_loaded = set(sys.modules) - before
    assert "app.evaluation.connection_abstraction" not in newly_loaded
    for drv in ("psycopg", "psycopg2", "oracledb", "cx_Oracle"):
        assert drv not in newly_loaded


def test_seven_span_assembly_and_secret_free_payload():
    from types import SimpleNamespace
    from app.trace.end_to_end_trace import build_end_to_end_trace
    from app.trace.end_to_end_trace_builders import (
        build_intent_span, build_retrieval_span, build_prompt_span,
        build_generation_span, build_validation_span, build_execution_span,
        build_security_span,
    )
    intent = build_intent_span(SimpleNamespace(
        extraction_version="intent_extraction_v1",
        intent=SimpleNamespace(normalized_query="who is alice",
                               intent_type="list", ambiguity_detected=False,
                               has_filter=True, has_aggregation=False,
                               has_grouping=False, has_ordering=False,
                               has_limit=False, requires_join=False,
                               has_time_range=False, signals=())), duration_ms=1.0)
    retrieval = build_retrieval_span(SimpleNamespace(
        k_requested=5, k_returned=1, retrieval_version="top_k_retrieval_v1",
        candidates=(SimpleNamespace(object_id="tbl.users", object_type="table",
                                    text="alice PII", score=0.9, rank=1,
                                    schema_hash="d" * 64),)), duration_ms=2.0)
    prompt = build_prompt_span(SimpleNamespace(
        prompt_sha256="e" * 64, prompt_char_count=10, intent_type="list",
        target_dialect="postgresql", rendered_prompt="SELECT alice",
        source_section_types=("schema",), source_item_ids=("s1",),
        input_version="sql_generation_input_v1"), duration_ms=3.0)
    generation = build_generation_span(SimpleNamespace(
        response=SimpleNamespace(provider_id="nvidia", model_id="nemotron",
                                 raw_text="SELECT 1", finish_reason="stop",
                                 prompt_sha256="e" * 64, output_sha256="f" * 64,
                                 latency_ms=42, token_usage=None),
        prompt_sha256="e" * 64, output_sha256="f" * 64))
    validation = build_validation_span((), valid=True, sql_sha256="f" * 64,
                                       duration_ms=1.0)
    security = build_security_span((SimpleNamespace(
        category=SimpleNamespace(value="read_only"),
        outcome=SimpleNamespace(value="allowed"),
        severity=SimpleNamespace(value="info"),
        reason_code="read_only_op", entry_hash="b" * 64),))
    execution = build_execution_span(SimpleNamespace(
        status="executed",
        plan=SimpleNamespace(effective_dialect=SimpleNamespace(value="postgresql")),
        execution_result=SimpleNamespace(sql_sha256="f" * 64, row_count=1,
                                         truncated=False, execution_error=None),
        error=None, warnings=()), duration_ms=5.0)

    trace = build_end_to_end_trace(
        trace_id="t1", request_id="r1",
        spans=(intent, retrieval, prompt, generation, validation, security, execution),
        job_id="j1", dialect="postgresql", nl_query_sha256="c" * 64,
        total_duration_ms=14.0)

    assert len(trace.spans) == 7
    assert trace.terminal_status.value == "completed"
    dumped = json.dumps(trace.to_payload())      # must not raise
    # secret-free: no raw NL / SQL / prompt / candidate text leaked anywhere
    for leak in ("alice", "SELECT", "PII"):
        assert leak.upper() not in dumped.upper()
    # but hashes and identifiers are present
    assert "e" * 64 in dumped and "f" * 64 in dumped
    assert '"stage": "intent"' in dumped and '"stage": "generation"' in dumped
