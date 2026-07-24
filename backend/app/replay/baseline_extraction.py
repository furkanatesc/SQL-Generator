"""end_to_end trace payload'indan baseline cikarimi (Sprint 27.4).

SAF: girdi bir dict'tir, I/O yoktur, EndToEndTrace nesnesi KURULMAZ.
app.trace.end_to_end_trace importu yalnizca stage/status literal'lerini tek
kaynaktan okumak icindir ("retrieval", "skipped" gibi string'leri kopyalamamak).
"""
from typing import Any, Mapping, Optional

from app.replay.contract import ReplayBaseline
from app.trace.end_to_end_trace import TraceSpanStatus, TraceStageKind

_SKIPPED = TraceSpanStatus.SKIPPED.value


def _spans_by_stage(payload: Mapping[str, Any]) -> dict:
    by_stage = {}
    for span in payload.get("spans") or ():
        if isinstance(span, Mapping) and span.get("stage"):
            by_stage[span["stage"]] = span
    return by_stage


def _measured(span: Optional[Mapping[str, Any]]) -> Optional[Mapping[str, Any]]:
    """Span yoksa ya da SKIPPED ise None — o boyut o gun olculmemistir."""
    if span is None or span.get("status") == _SKIPPED:
        return None
    return span


def _detail(span: Mapping[str, Any]) -> Mapping[str, Any]:
    detail = span.get("detail")
    return detail if isinstance(detail, Mapping) else {}


def extract_baseline(
    trace_payload: Optional[Mapping[str, Any]],
) -> Optional[ReplayBaseline]:
    """end_to_end payload'indan ReplayBaseline uretir; payload bossa None."""
    if not trace_payload:
        return None

    by_stage = _spans_by_stage(trace_payload)

    retrieval_tables = None
    retrieval = _measured(by_stage.get(TraceStageKind.RETRIEVAL.value))
    if retrieval is not None:
        candidates = _detail(retrieval).get("candidates") or ()
        retrieval_tables = tuple(sorted({
            str(c["object_id"])
            for c in candidates
            if isinstance(c, Mapping)
            and c.get("object_type") == "table"
            and c.get("object_id")
        }))

    validation_valid = None
    validation_issue_types = None
    validation = _measured(by_stage.get(TraceStageKind.VALIDATION.value))
    if validation is not None:
        detail = _detail(validation)
        validation_valid = bool(detail.get("valid"))
        # DIKKAT: trace tarafinda alan adi "category" (ValidationIssue.category);
        # uretim pipeline'inin hata sozlugunde ayni eksen "type" olarak gecer.
        validation_issue_types = tuple(sorted({
            str(i["category"])
            for i in (detail.get("issues") or ())
            if isinstance(i, Mapping) and i.get("category")
        }))

    security_denied = None
    security = _measured(by_stage.get(TraceStageKind.SECURITY.value))
    if security is not None:
        security_denied = tuple(sorted({
            str(c.get("reason_code") or c.get("category") or "denied")
            for c in (_detail(security).get("checks") or ())
            if isinstance(c, Mapping) and c.get("outcome") == "denied"
        }))

    return ReplayBaseline(
        trace_id=trace_payload.get("trace_id"),
        terminal_status=trace_payload.get("terminal_status"),
        retrieval_tables=retrieval_tables,
        validation_valid=validation_valid,
        validation_issue_types=validation_issue_types,
        security_denied=security_denied,
    )
