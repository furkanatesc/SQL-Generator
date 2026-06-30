# backend/tests/trace/test_end_to_end_trace_builders.py
from types import SimpleNamespace

import pytest

from app.trace.end_to_end_trace import (
    TraceStageKind, TraceSpanStatus, ExecutionSpanDetail, EndToEndTraceError,
)
from app.trace.end_to_end_trace_builders import build_execution_span


def _executed_outcome(warnings=()):
    return SimpleNamespace(
        status="executed",
        plan=SimpleNamespace(effective_dialect=SimpleNamespace(value="postgresql")),
        execution_result=SimpleNamespace(
            sql_sha256="a" * 64, row_count=2, truncated=False, execution_error=None),
        error=None, warnings=tuple(warnings))


def test_executed_maps_to_ok():
    span = build_execution_span(_executed_outcome(), duration_ms=4.0)
    assert span.stage == TraceStageKind.EXECUTION
    assert span.status == TraceSpanStatus.OK
    assert span.duration_ms == 4.0
    assert isinstance(span.detail, ExecutionSpanDetail)
    assert span.detail.execution_status == "executed"
    assert span.detail.dialect == "postgresql"
    assert span.detail.sql_sha256 == "a" * 64
    assert span.detail.row_count == 2


def test_executed_with_warnings_maps_to_warning():
    span = build_execution_span(_executed_outcome(warnings=("row cap",)))
    assert span.status == TraceSpanStatus.WARNING


def test_blocked_maps_to_error_and_sanitizes():
    outcome = SimpleNamespace(
        status="blocked_live_connection",
        plan=SimpleNamespace(effective_dialect=SimpleNamespace(value="oracle")),
        execution_result=None,
        error="live connection blocked; password=hunter2", warnings=())
    span = build_execution_span(outcome)
    assert span.status == TraceSpanStatus.ERROR
    assert span.detail.execution_status == "blocked_live_connection"
    assert span.detail.dialect == "oracle"
    assert "hunter2" not in (span.detail.error_message or "")


def test_rejected_maps_to_error():
    outcome = SimpleNamespace(
        status="rejected", plan=None, execution_result=None,
        error="rejected by orchestrator", warnings=())
    span = build_execution_span(outcome)
    assert span.status == TraceSpanStatus.ERROR
    assert span.detail.execution_status == "rejected"
    assert span.detail.dialect is None


def test_unknown_status_raises():
    outcome = SimpleNamespace(status="weird", plan=None, execution_result=None,
                              error=None, warnings=())
    with pytest.raises(EndToEndTraceError):
        build_execution_span(outcome)


def test_no_raw_sql_carried():
    # the builder only ever reads sql_sha256, never a raw sql attribute
    outcome = _executed_outcome()
    span = build_execution_span(outcome)
    assert not hasattr(span.detail, "sql")


# --- security span tests ---
from app.trace.end_to_end_trace import SecuritySpanDetail  # noqa: E402
from app.trace.end_to_end_trace_builders import build_security_span  # noqa: E402


def _evt(outcome, *, category="read_only", severity="info",
         reason_code="read_only_select", entry_hash="b" * 64):
    return SimpleNamespace(
        category=SimpleNamespace(value=category),
        outcome=SimpleNamespace(value=outcome),
        severity=SimpleNamespace(value=severity),
        reason_code=reason_code, entry_hash=entry_hash)


def test_security_empty_is_skipped():
    span = build_security_span(())
    assert span.stage == TraceStageKind.SECURITY
    assert span.status == TraceSpanStatus.SKIPPED
    assert isinstance(span.detail, SecuritySpanDetail)
    assert span.detail.checks == ()


def test_security_all_allowed_is_ok():
    span = build_security_span((_evt("allowed"), _evt("allowed")))
    assert span.status == TraceSpanStatus.OK
    assert len(span.detail.checks) == 2
    assert span.detail.checks[0].category == "read_only"
    assert span.detail.checks[0].audit_entry_hash == "b" * 64


def test_security_denied_is_error():
    span = build_security_span((_evt("allowed"), _evt("denied", category="tenant_boundary")))
    assert span.status == TraceSpanStatus.ERROR


def test_security_error_outcome_is_error():
    span = build_security_span((_evt("error"),))
    assert span.status == TraceSpanStatus.ERROR


def test_security_flagged_is_warning():
    span = build_security_span((_evt("flagged", category="query_risk"),))
    assert span.status == TraceSpanStatus.WARNING


def test_security_requires_approval_is_warning():
    span = build_security_span((_evt("requires_approval", category="approval"),))
    assert span.status == TraceSpanStatus.WARNING


def test_security_none_is_skipped():
    span = build_security_span(None)
    assert span.stage == TraceStageKind.SECURITY
    assert span.status == TraceSpanStatus.SKIPPED
    assert span.detail.checks == ()
