# backend/app/trace/end_to_end_trace_builders.py
"""Sprint 27.0 — duck-typed span builders for the end-to-end trace.

Builders read attributes off stage outputs WITHOUT hard-importing their
modules, so importing this module does not pull app.evaluation or DB
drivers. 27.1 adds the remaining stage builders the same way.
"""
from __future__ import annotations

from typing import Optional

from app.trace.end_to_end_trace import (
    EndToEndTraceError, ExecutionSpanDetail, GenerationSpanDetail, IntentSpanDetail,
    PromptSpanDetail,
    RetrievalCandidateRef, RetrievalSpanDetail,
    SecurityCheck, SecuritySpanDetail,
    TraceSpan, TraceSpanStatus, TraceStageKind,
    ValidationIssue, ValidationSpanDetail,
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


_INTENT_FLAG_NAMES = (
    "has_filter", "has_aggregation", "has_grouping", "has_ordering",
    "has_limit", "requires_join", "has_time_range",
)


def build_intent_span(result, *, duration_ms: Optional[float] = None) -> TraceSpan:
    """Normalize a (duck-typed) IntentExtractionResult into an INTENT span.

    Reads result.intent.{intent_type, <flag booleans>, ambiguity_detected,
    signals[].name} and result.extraction_version. Secret-free: never reads
    normalized_query or signal value/reason. None result -> SKIPPED.
    """
    if result is None:
        return TraceSpan(stage=TraceStageKind.INTENT, status=TraceSpanStatus.SKIPPED)
    intent = getattr(result, "intent", None)
    if intent is None:
        raise EndToEndTraceError("intent result missing .intent")
    intent_type = _status_str(getattr(intent, "intent_type", None))
    if not intent_type:
        raise EndToEndTraceError("intent missing intent_type")
    flags = tuple(name for name in _INTENT_FLAG_NAMES if getattr(intent, name, False))
    ambiguity = bool(getattr(intent, "ambiguity_detected", False))
    signal_names = tuple(
        _status_str(getattr(s, "name", None))
        for s in (getattr(intent, "signals", ()) or ())
        if getattr(s, "name", None) is not None
    )
    detail = IntentSpanDetail(
        intent_type=intent_type, flags=flags, ambiguity_detected=ambiguity,
        signal_names=signal_names,
        extraction_version=getattr(result, "extraction_version", None))
    status = (TraceSpanStatus.WARNING
              if ambiguity or intent_type == "unknown" else TraceSpanStatus.OK)
    return TraceSpan(stage=TraceStageKind.INTENT, status=status,
                     duration_ms=duration_ms, detail=detail)


def build_retrieval_span(result, *, duration_ms: Optional[float] = None) -> TraceSpan:
    """Normalize a (duck-typed) TopKRetrievalResult into a RETRIEVAL span.

    Reads k_requested/k_returned/retrieval_version and per-candidate
    object_id/object_type/score/rank/schema_hash. Secret-free: never reads
    candidate .text or the query text. None -> SKIPPED; k_returned==0 -> WARNING.
    """
    if result is None:
        return TraceSpan(stage=TraceStageKind.RETRIEVAL, status=TraceSpanStatus.SKIPPED)
    candidates = tuple(
        RetrievalCandidateRef(
            object_id=_status_str(getattr(c, "object_id", None)),
            object_type=_status_str(getattr(c, "object_type", None)),
            score=getattr(c, "score", None),
            rank=getattr(c, "rank", None),
            schema_hash=getattr(c, "schema_hash", None),
        )
        for c in (getattr(result, "candidates", ()) or ())
    )
    k_returned = getattr(result, "k_returned", None)
    detail = RetrievalSpanDetail(
        k_requested=getattr(result, "k_requested", None),
        k_returned=k_returned, candidates=candidates,
        retrieval_version=getattr(result, "retrieval_version", None))
    no_results = (k_returned == 0) or (k_returned is None and not candidates)
    status = TraceSpanStatus.WARNING if no_results else TraceSpanStatus.OK
    return TraceSpan(stage=TraceStageKind.RETRIEVAL, status=status,
                     duration_ms=duration_ms, detail=detail)


def build_prompt_span(gen_input, *, duration_ms: Optional[float] = None) -> TraceSpan:
    """Normalize a (duck-typed) SQLGenerationInputResult into a PROMPT span.

    Reads prompt_sha256/prompt_char_count/intent_type/target_dialect/
    source_section_types/source_item_ids/input_version. Secret-free: never reads
    rendered_prompt/raw_query/normalized_query. None -> SKIPPED.
    """
    if gen_input is None:
        return TraceSpan(stage=TraceStageKind.PROMPT, status=TraceSpanStatus.SKIPPED)
    detail = PromptSpanDetail(
        prompt_sha256=getattr(gen_input, "prompt_sha256", None),
        prompt_char_count=getattr(gen_input, "prompt_char_count", None),
        intent_type=_status_str(getattr(gen_input, "intent_type", None)),
        target_dialect=_status_str(getattr(gen_input, "target_dialect", None)),
        source_section_types=tuple(getattr(gen_input, "source_section_types", ()) or ()),
        source_item_ids=tuple(getattr(gen_input, "source_item_ids", ()) or ()),
        input_version=getattr(gen_input, "input_version", None))
    return TraceSpan(stage=TraceStageKind.PROMPT, status=TraceSpanStatus.OK,
                     duration_ms=duration_ms, detail=detail)


_GENERATION_ERROR_FINISH = {"error", "content_filter", "null", "none", ""}
_GENERATION_WARNING_FINISH = {"length", "max_tokens", "truncated"}


def build_generation_span(provider_result, *, duration_ms: Optional[float] = None) -> TraceSpan:
    """Normalize a (duck-typed) SQLGenerationProviderResult into a GENERATION span.

    Reads .response.{provider_id,model_id,finish_reason,latency_ms,token_usage}
    and prompt_sha256/output_sha256 (top-level or on .response). Secret-free:
    never reads raw_text/generated_sql_text. None -> SKIPPED. Missing output or
    error finish_reason -> ERROR; truncation finish_reason -> WARNING.
    duration_ms falls back to response.latency_ms when not supplied.
    """
    if provider_result is None:
        return TraceSpan(stage=TraceStageKind.GENERATION, status=TraceSpanStatus.SKIPPED)
    response = getattr(provider_result, "response", None) or provider_result
    finish_reason = _status_str(getattr(response, "finish_reason", None))
    output_sha256 = (getattr(provider_result, "output_sha256", None)
                     or getattr(response, "output_sha256", None))
    usage = getattr(response, "token_usage", None)
    if duration_ms is None:
        duration_ms = getattr(response, "latency_ms", None)
    detail = GenerationSpanDetail(
        provider_id=getattr(response, "provider_id", None),
        model_id=getattr(response, "model_id", None),
        finish_reason=finish_reason,
        prompt_sha256=(getattr(provider_result, "prompt_sha256", None)
                       or getattr(response, "prompt_sha256", None)),
        output_sha256=output_sha256,
        prompt_tokens=getattr(usage, "prompt_tokens", None),
        completion_tokens=getattr(usage, "completion_tokens", None),
        total_tokens=getattr(usage, "total_tokens", None))
    fr = (finish_reason or "").lower()
    if not output_sha256 or fr in _GENERATION_ERROR_FINISH:
        status = TraceSpanStatus.ERROR
    elif fr in _GENERATION_WARNING_FINISH:
        status = TraceSpanStatus.WARNING
    else:
        status = TraceSpanStatus.OK
    return TraceSpan(stage=TraceStageKind.GENERATION, status=status,
                     duration_ms=duration_ms, detail=detail)


def build_validation_span(issues, *, valid, sql_sha256: Optional[str] = None,
                          duration_ms: Optional[float] = None) -> TraceSpan:
    """Synthesize a VALIDATION span from a generic issue sequence + valid flag.

    Each issue is duck-typed: category = .category or .type; also reads .stage,
    .severity, .reason_code (falling back to .type). Secret-free: never reads
    .message (SQL/column fragments). issues is None -> SKIPPED; valid False ->
    ERROR; valid with issues -> WARNING; clean -> OK.
    """
    if issues is None:
        return TraceSpan(stage=TraceStageKind.VALIDATION, status=TraceSpanStatus.SKIPPED)
    normalized = tuple(
        ValidationIssue(
            category=(_status_str(getattr(e, "category", None)
                                  or getattr(e, "type", None)) or "unknown"),
            stage=_status_str(getattr(e, "stage", None)),
            severity=_status_str(getattr(e, "severity", None)),
            reason_code=(getattr(e, "reason_code", None) or getattr(e, "type", None)),
        )
        for e in issues
    )
    if not valid:
        status = TraceSpanStatus.ERROR
    elif normalized:
        status = TraceSpanStatus.WARNING
    else:
        status = TraceSpanStatus.OK
    detail = ValidationSpanDetail(valid=bool(valid), sql_sha256=sql_sha256,
                                  issues=normalized)
    return TraceSpan(stage=TraceStageKind.VALIDATION, status=status,
                     duration_ms=duration_ms, detail=detail)
