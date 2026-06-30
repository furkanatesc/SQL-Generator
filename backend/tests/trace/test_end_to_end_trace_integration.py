# backend/tests/trace/test_end_to_end_trace_integration.py
import json
from types import SimpleNamespace

from app.trace.end_to_end_trace import (
    TraceStageKind, TraceSpanStatus, TraceTerminalStatus, build_end_to_end_trace,
)
from app.trace.end_to_end_trace_builders import build_execution_span, build_security_span


def test_end_to_end_happy_path_assembles_and_serializes():
    security = build_security_span((
        SimpleNamespace(category=SimpleNamespace(value="read_only"),
                        outcome=SimpleNamespace(value="allowed"),
                        severity=SimpleNamespace(value="info"),
                        reason_code="read_only_select", entry_hash="b" * 64),))
    execution = build_execution_span(SimpleNamespace(
        status="executed",
        plan=SimpleNamespace(effective_dialect=SimpleNamespace(value="postgresql")),
        execution_result=SimpleNamespace(
            sql_sha256="a" * 64, row_count=5, truncated=False, execution_error=None),
        error=None, warnings=()), duration_ms=12.0)

    trace = build_end_to_end_trace(
        trace_id="trace-1", request_id="req-1", spans=(security, execution),
        dialect="postgresql", nl_query_sha256="c" * 64, total_duration_ms=20.0)

    assert trace.terminal_status == TraceTerminalStatus.COMPLETED
    assert trace.terminal_stage == TraceStageKind.EXECUTION
    payload = trace.to_payload()
    json.dumps(payload)  # must not raise
    assert [s["stage"] for s in payload["spans"]] == ["security", "execution"]


def test_end_to_end_blocked_path():
    execution = build_execution_span(SimpleNamespace(
        status="blocked_live_connection",
        plan=SimpleNamespace(effective_dialect=SimpleNamespace(value="oracle")),
        execution_result=None, error="live connection blocked", warnings=()))
    trace = build_end_to_end_trace(trace_id="t", request_id="r", spans=(execution,))
    assert trace.terminal_status == TraceTerminalStatus.BLOCKED
    assert trace.terminal_stage == TraceStageKind.EXECUTION
    assert trace.spans[0].status == TraceSpanStatus.ERROR
