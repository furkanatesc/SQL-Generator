# backend/app/trace/end_to_end_trace_builders.py
"""Sprint 27.0 — duck-typed span builders for the end-to-end trace.

Builders read attributes off stage outputs WITHOUT hard-importing their
modules, so importing this module does not pull app.evaluation or DB
drivers. 27.1 adds the remaining stage builders the same way.
"""
from __future__ import annotations

from typing import Optional

from app.trace.end_to_end_trace import (
    EndToEndTraceError, ExecutionSpanDetail, SecurityCheck, SecuritySpanDetail,
    TraceSpan, TraceSpanStatus, TraceStageKind,
)
from app.trace.redaction import redact_sensitive_text

_EXEC_STATUSES = {"executed", "blocked_live_connection", "rejected"}


def _status_str(raw) -> str:
    """Reduce an enum-or-str status to its string value."""
    return getattr(raw, "value", raw)


def build_execution_span(outcome, *, duration_ms: Optional[float] = None) -> TraceSpan:
    """Normalize a (duck-typed) SQLConnectionAwareExecutionOutcome into a span.

    Reads: .status, .plan.effective_dialect, .execution_result.{sql_sha256,
    row_count, truncated, execution_error}, .error, .warnings. Secret-free:
    only sql_sha256 (never raw sql), and error text is sanitized.
    """
    status = _status_str(getattr(outcome, "status", None))
    if status not in _EXEC_STATUSES:
        raise EndToEndTraceError(f"unknown execution status: {status!r}")

    plan = getattr(outcome, "plan", None)
    dialect = None
    if plan is not None and getattr(plan, "effective_dialect", None) is not None:
        dialect = _status_str(plan.effective_dialect)

    result = getattr(outcome, "execution_result", None)
    sql_sha256 = getattr(result, "sql_sha256", None) if result is not None else None
    row_count = getattr(result, "row_count", None) if result is not None else None
    truncated = getattr(result, "truncated", None) if result is not None else None
    result_error = getattr(result, "execution_error", None) if result is not None else None

    raw_error = getattr(outcome, "error", None) or result_error
    error_message = redact_sensitive_text(raw_error) if raw_error else None

    warnings = getattr(outcome, "warnings", ()) or ()
    if status == "executed":
        span_status = TraceSpanStatus.WARNING if warnings else TraceSpanStatus.OK
    else:
        span_status = TraceSpanStatus.ERROR

    detail = ExecutionSpanDetail(
        execution_status=status, dialect=dialect, sql_sha256=sql_sha256,
        row_count=row_count, truncated=truncated,
        error_code=None, error_message=error_message)
    return TraceSpan(stage=TraceStageKind.EXECUTION, status=span_status,
                     duration_ms=duration_ms, detail=detail)


_DENY_OUTCOMES = {"denied", "error"}
_WARN_OUTCOMES = {"flagged", "requires_approval"}


def build_security_span(audit_events) -> TraceSpan:
    """Normalize a sequence of (duck-typed) AuditEvents into a security span.

    Reads each event's .category/.outcome/.severity (enum-or-str), .reason_code,
    .entry_hash. Empty sequence -> SKIPPED (security stage did not run).
    """
    checks = tuple(
        SecurityCheck(
            category=_status_str(getattr(e, "category", None)),
            outcome=_status_str(getattr(e, "outcome", None)),
            severity=_status_str(getattr(e, "severity", None)),
            reason_code=getattr(e, "reason_code", None),
            audit_entry_hash=getattr(e, "entry_hash", None),
        )
        for e in (audit_events or ())
    )
    if not checks:
        status = TraceSpanStatus.SKIPPED
    elif any(c.outcome in _DENY_OUTCOMES for c in checks):
        status = TraceSpanStatus.ERROR
    elif any(c.outcome in _WARN_OUTCOMES for c in checks):
        status = TraceSpanStatus.WARNING
    else:
        status = TraceSpanStatus.OK
    return TraceSpan(stage=TraceStageKind.SECURITY, status=status,
                     detail=SecuritySpanDetail(checks=checks))
