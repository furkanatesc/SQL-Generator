"""LLM usage aggregation — SAF (Sprint 27.8).

I/O yok. datetime.now() ASLA cagrilmaz; yalnizca VAR OLAN created_at floor'lanir.
Percentile NEAREST-RANK'tir (ceil(p*n)). Yalniz stdlib + app.llm_usage.contract/pricing.
"""
import dataclasses
from datetime import timezone
from math import ceil
from typing import Optional, Tuple

from app.llm_usage.contract import (
    LLM_USAGE_CONTRACT_VERSION,
    LLMUsageReport,
    LatencyStats,
    ModelUsage,
    PricingInfo,
    ProviderUsage,
    UsageBucket,
    UsageTotals,
)
from app.llm_usage.pricing import cost_for

MAX_USAGE_BUCKETS = 500

_GENERATION_STAGE = "generation"
_SKIPPED = "skipped"


def _is_number(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _sum_tokens(events, field: str) -> int:
    return sum(e[field] for e in events if _is_number(e.get(field)))


def _percentile(sorted_vals: list, p: float) -> Optional[float]:
    if not sorted_vals:
        return None
    rank = max(1, ceil(p * len(sorted_vals)))
    return sorted_vals[rank - 1]


def _floor_iso(created_at, bucket_kind: str) -> str:
    dt_obj = created_at
    if dt_obj.tzinfo is None:
        dt_obj = dt_obj.replace(tzinfo=timezone.utc)
    dt_obj = dt_obj.astimezone(timezone.utc)
    if bucket_kind == "hour":
        floored = dt_obj.replace(minute=0, second=0, microsecond=0)
    else:  # "day"
        floored = dt_obj.replace(hour=0, minute=0, second=0, microsecond=0)
    return floored.isoformat()


def _event_cost(event, price_table) -> Optional[float]:
    return cost_for(event.get("prompt_tokens"), event.get("completion_tokens"),
                    price_table.get(event.get("model_id")))


def generation_events(trace_items) -> list:
    """Her (created_at, payload) icin KOSAN GENERATION span'inden bir olay dict'i.

    stage=='generation' + status!='skipped'. Alanlar span['detail'] alt-sozlugunden.
    Generation span'i yoksa ya da skipped ise o trace atlanir (LLM kosmamis).
    """
    events = []
    for created_at, payload in trace_items:
        spans = payload.get("spans") or []
        gen = None
        for s in spans:
            if isinstance(s, dict) and s.get("stage") == _GENERATION_STAGE:
                gen = s
                break
        if gen is None or gen.get("status") == _SKIPPED:
            continue
        detail = gen.get("detail") or {}
        events.append({
            "created_at": created_at,
            "provider_id": detail.get("provider_id"),
            "model_id": detail.get("model_id"),
            "finish_reason": detail.get("finish_reason"),
            "prompt_tokens": detail.get("prompt_tokens"),
            "completion_tokens": detail.get("completion_tokens"),
            "total_tokens": detail.get("total_tokens"),
            "duration_ms": gen.get("duration_ms"),
        })
    return events


def aggregate_usage(events, key_field: str, price_table, make) -> Tuple:
    """events'i key_field'e (model_id/provider_id) gore gruplar. None anahtar -> 'unknown'.

    Grup cost'u = fiyatli event maliyetlerinin toplami; hicbiri fiyatli degilse None.
    Siralama: total_tokens AZALAN, esitlikte anahtar ARTAN. make = ModelUsage/ProviderUsage.
    """
    groups: dict = {}
    for e in events:
        k = e.get(key_field) or "unknown"
        groups.setdefault(k, []).append(e)
    rows = []
    for k in groups:
        evs = groups[k]
        prompt = _sum_tokens(evs, "prompt_tokens")
        completion = _sum_tokens(evs, "completion_tokens")
        total = _sum_tokens(evs, "total_tokens")
        priced = [c for c in (_event_cost(e, price_table) for e in evs) if c is not None]
        est = round(sum(priced), 6) if priced else None
        rows.append((k, len(evs), prompt, completion, total, est))
    rows.sort(key=lambda r: (-r[4], r[0]))  # total_tokens DESC, anahtar ASC
    return tuple(make(*r) for r in rows)


def latency_stats(events) -> LatencyStats:
    durs = sorted(e["duration_ms"] for e in events if _is_number(e.get("duration_ms")))
    return LatencyStats(count=len(durs), p50=_percentile(durs, 0.50),
                        p95=_percentile(durs, 0.95), p99=_percentile(durs, 0.99))


def finish_reason_counts(events) -> dict:
    counts: dict = {}
    for e in events:
        fr = e.get("finish_reason")
        if fr:
            counts[fr] = counts.get(fr, 0) + 1
    return counts


def bucket_usage_timeseries(events, bucket: str, price_table) -> Tuple[Tuple[UsageBucket, ...], bool]:
    groups: dict = {}
    for e in events:
        created_at = e.get("created_at")
        if created_at is None or not hasattr(created_at, "tzinfo"):
            continue  # timeseries yalniz datetime damgali olaylari kapsar (totals'ta yine sayilir)
        start = _floor_iso(created_at, bucket)
        groups.setdefault(start, []).append(e)

    starts = sorted(groups)
    truncated = False
    if len(starts) > MAX_USAGE_BUCKETS:
        starts = starts[-MAX_USAGE_BUCKETS:]
        truncated = True

    buckets = []
    for start in starts:
        evs = groups[start]
        total = _sum_tokens(evs, "total_tokens")
        priced = [c for c in (_event_cost(e, price_table) for e in evs) if c is not None]
        est = round(sum(priced), 6) if priced else None
        buckets.append(UsageBucket(bucket_start=start, request_count=len(evs),
                                   total_tokens=total, estimated_cost=est))
    return tuple(buckets), truncated


def compute_llm_usage(*, trace_items, window, currency: str, price_table, bucket: str) -> LLMUsageReport:
    events = generation_events(trace_items)

    prompt = _sum_tokens(events, "prompt_tokens")
    completion = _sum_tokens(events, "completion_tokens")
    total = _sum_tokens(events, "total_tokens")
    priced_costs = [c for c in (_event_cost(e, price_table) for e in events) if c is not None]
    est_total = round(sum(priced_costs), 6) if priced_costs else 0.0
    unpriced = sum(1 for e in events if price_table.get(e.get("model_id")) is None)
    totals = UsageTotals(request_count=len(events), prompt_tokens=prompt,
                         completion_tokens=completion, total_tokens=total,
                         estimated_cost=est_total, unpriced_request_count=unpriced)

    by_model = aggregate_usage(events, "model_id", price_table, ModelUsage)
    by_provider = aggregate_usage(events, "provider_id", price_table, ProviderUsage)
    latency = latency_stats(events)
    finish = finish_reason_counts(events)
    ts_buckets, ts_truncated = bucket_usage_timeseries(events, bucket, price_table)

    seen_models = {e.get("model_id") for e in events if e.get("model_id")}
    priced_models = tuple(sorted(m for m in seen_models if m in price_table))
    missing_models = tuple(sorted(m for m in seen_models if m not in price_table))
    pricing = PricingInfo(models_priced=priced_models, models_missing_price=missing_models)

    window = dataclasses.replace(window, generation_count=len(events),
                                 timeseries_truncated=ts_truncated)

    return LLMUsageReport(
        version=LLM_USAGE_CONTRACT_VERSION, currency=currency, window=window,
        totals=totals, by_model=by_model, by_provider=by_provider,
        latency_ms=latency, finish_reasons=finish, timeseries=ts_buckets, pricing=pricing)
