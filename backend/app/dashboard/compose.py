"""Admin dashboard aggregation — SAF (Sprint 27.7).

I/O yok. datetime.now() ASLA cagrilmaz; yalnizca VAR OLAN damgalar floor'lanir.
Percentile NEAREST-RANK'tir (ceil(p*n)). app.metrics/app.errors izinli; app.trace ASLA.
"""
from datetime import timezone
from math import ceil
from typing import Optional, Tuple

from app.dashboard.contract import (
    FeedbackSummary,
    RecentTrace,
    TimeseriesBucket,
    TopError,
)
from app.errors import UnknownErrorCodeError, category_of

MAX_TIMESERIES_BUCKETS = 500

_DENY_TERMINALS = frozenset({"failed", "blocked", "rejected"})


def _percentile(sorted_vals: list, p: float) -> Optional[float]:
    if not sorted_vals:
        return None
    rank = max(1, ceil(p * len(sorted_vals)))
    return sorted_vals[rank - 1]


def _floor_iso(created_at, bucket_kind: str) -> str:
    # created_at: datetime (aware ya da naive->UTC varsayilir). Yalnizca floor'lanir.
    dt_obj = created_at
    if dt_obj.tzinfo is None:
        dt_obj = dt_obj.replace(tzinfo=timezone.utc)
    dt_obj = dt_obj.astimezone(timezone.utc)
    if bucket_kind == "hour":
        floored = dt_obj.replace(minute=0, second=0, microsecond=0)
    else:  # "day"
        floored = dt_obj.replace(hour=0, minute=0, second=0, microsecond=0)
    return floored.isoformat()


def bucket_timeseries(trace_items, bucket_kind: str) -> Tuple[Tuple[TimeseriesBucket, ...], bool]:
    groups: dict = {}
    for created_at, payload in trace_items:
        start = _floor_iso(created_at, bucket_kind)
        groups.setdefault(start, []).append(payload)

    starts = sorted(groups)  # ISO (ayni offset) lexicographic == kronolojik
    truncated = False
    if len(starts) > MAX_TIMESERIES_BUCKETS:
        starts = starts[-MAX_TIMESERIES_BUCKETS:]  # en yeni N
        truncated = True

    buckets = []
    for start in starts:
        payloads = groups[start]
        total = len(payloads)
        completed = sum(1 for p in payloads if p.get("terminal_status") == "completed")
        error_count = sum(1 for p in payloads
                          if p.get("terminal_status") in _DENY_TERMINALS)
        success_rate = round(completed / total, 4) if total else None
        durations = sorted(
            p["total_duration_ms"] for p in payloads
            if isinstance(p.get("total_duration_ms"), (int, float))
            and not isinstance(p.get("total_duration_ms"), bool))
        buckets.append(TimeseriesBucket(
            bucket_start=start, total=total, success_rate=success_rate,
            error_count=error_count, p95_ms=_percentile(durations, 0.95)))
    return tuple(buckets), truncated


def top_errors(metrics_payload, top_n: int) -> Tuple[TopError, ...]:
    by_code = (metrics_payload.get("errors") or {}).get("by_code") or {}
    # sayiya gore AZALAN, esitlikte kod ARTAN (determinist)
    ranked = sorted(by_code.items(), key=lambda kv: (-kv[1], kv[0]))[:top_n]
    out = []
    for code, count in ranked:
        try:
            category = category_of(code).value
        except UnknownErrorCodeError:
            category = "unknown"
        out.append(TopError(code=code, category=category, count=count))
    return tuple(out)


def summarize_feedback(rows) -> FeedbackSummary:
    by_verdict: dict = {}
    by_category: dict = {}
    for r in rows or ():
        verdict = r.get("verdict")
        if verdict:
            by_verdict[verdict] = by_verdict.get(verdict, 0) + 1
        category = r.get("category")
        if category:  # None/bos kategori (or. correct verdict) atlanir
            by_category[category] = by_category.get(category, 0) + 1
    return FeedbackSummary(total=len(rows or ()), by_verdict=by_verdict, by_category=by_category)


def shape_recent(trace_items, recent_limit: int) -> Tuple[RecentTrace, ...]:
    out = []
    for created_at, payload in list(trace_items)[:recent_limit]:
        created_iso = created_at.isoformat() if hasattr(created_at, "isoformat") else created_at
        out.append(RecentTrace(
            job_id=payload.get("job_id"),
            trace_id=payload.get("trace_id"),
            terminal_status=payload.get("terminal_status"),
            dialect=payload.get("dialect"),
            total_duration_ms=payload.get("total_duration_ms"),
            created_at=created_iso))
    return tuple(out)
