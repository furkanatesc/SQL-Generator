"""Metrics aggregation — SAF (Sprint 27.6).

I/O yok. end_to_end trace payload listesi + pencere -> MetricsReport.
app.errors izinlidir (kategori eslemesi); app.trace ASLA import edilmez.
Percentile NEAREST-RANK'tir: sirali liste + ceil(p*n) indeksi -> determinist.
"""
from math import ceil
from typing import List, Mapping, Optional

from app.errors import UnknownErrorCodeError, category_of

from app.metrics.contract import (
    METRICS_CONTRACT_VERSION, ErrorMetrics, LatencyMetrics, MetricsReport,
    MetricsWindow, OutcomeMetrics,
)

# PROMPT ve EXECUTION asamalari kirilimda kasitli haric (spec kapsam disi §2).
_STAGES = ("intent", "retrieval", "generation", "security", "validation")

# app.trace'ten MIRROR'lanmis (saf katman app.trace import edemez): guvenlik
# span'inde bir check bu outcome'a sahipse ERROR sayilir (bkz.
# end_to_end_trace_builders.py::_DENY_OUTCOMES).
_SECURITY_DENY_OUTCOMES = frozenset({"denied", "error"})


def _percentile(sorted_vals: list, p: float) -> Optional[float]:
    # nearest-rank: rank = ceil(p * n), 1-based; bos liste -> None.
    if not sorted_vals:
        return None
    rank = max(1, ceil(p * len(sorted_vals)))
    return sorted_vals[rank - 1]


def _inc(counter: dict, key) -> None:
    counter[key] = counter.get(key, 0) + 1


def _error_codes_from_span(span) -> list:
    # Once attributes.reason_code (INTENT/RETRIEVAL canli yolu); yoksa typed detail.
    attrs = span.get("attributes") or {}
    code = attrs.get("reason_code")
    if code:
        return [code]
    codes = []
    detail = span.get("detail") or {}
    for issue in detail.get("issues") or []:            # VALIDATION
        rc = (issue or {}).get("reason_code")
        if rc:
            codes.append(rc)
    for check in detail.get("checks") or []:            # SECURITY (yalniz deny)
        if (check or {}).get("outcome") in _SECURITY_DENY_OUTCOMES:
            rc = (check or {}).get("reason_code")
            if rc:
                codes.append(rc)
    return codes


def compute_metrics(payloads: List[Mapping], window: MetricsWindow) -> MetricsReport:
    total = len(payloads)

    # --- outcome ---
    ts_counts: dict = {}
    for pl in payloads:
        st = pl.get("terminal_status")
        if st is not None:
            _inc(ts_counts, st)
    completed = ts_counts.get("completed", 0)
    success_rate = round(completed / total, 4) if total else None
    outcome = OutcomeMetrics(total=total, terminal_status=ts_counts,
                             success_rate=success_rate)

    # --- errors (ERROR span'lerin kodu: attributes.reason_code veya typed detail) ---
    by_code: dict = {}
    by_category: dict = {}
    for pl in payloads:
        for span in pl.get("spans", []) or []:
            if span.get("status") != "error":
                continue
            for code in _error_codes_from_span(span):
                _inc(by_code, code)
                try:
                    category = category_of(code).value
                except UnknownErrorCodeError:
                    category = "unknown"
                _inc(by_category, category)
    errors = ErrorMetrics(by_code=by_code, by_category=by_category)

    # --- latency (trace-kok total_duration_ms) ---
    durations = sorted(
        pl["total_duration_ms"] for pl in payloads
        if isinstance(pl.get("total_duration_ms"), (int, float))
        and not isinstance(pl.get("total_duration_ms"), bool))
    if durations:
        latency = LatencyMetrics(
            count=len(durations),
            p50=_percentile(durations, 0.50),
            p95=_percentile(durations, 0.95),
            p99=_percentile(durations, 0.99),
            min=durations[0], max=durations[-1],
            mean=round(sum(durations) / len(durations), 2))
    else:
        latency = LatencyMetrics(count=0, p50=None, p95=None, p99=None,
                                 min=None, max=None, mean=None)

    # --- stages (stage -> span status dagilimi) ---
    stages: dict = {stg: {} for stg in _STAGES}
    for pl in payloads:
        for span in pl.get("spans", []) or []:
            stg = span.get("stage")
            status = span.get("status")
            if stg in stages and status:
                _inc(stages[stg], status)

    return MetricsReport(
        version=METRICS_CONTRACT_VERSION, window=window, outcome=outcome,
        errors=errors, latency_ms=latency, stages=stages)
