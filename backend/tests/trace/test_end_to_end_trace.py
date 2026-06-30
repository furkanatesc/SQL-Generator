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
