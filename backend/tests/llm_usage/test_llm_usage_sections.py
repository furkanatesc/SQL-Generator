from datetime import datetime, timezone
from app.llm_usage import (
    generation_events, aggregate_usage, latency_stats, finish_reason_counts,
    bucket_usage_timeseries, MAX_USAGE_BUCKETS, ModelUsage, ProviderUsage,
)


def _gen_span(provider="nvidia", model="m1", finish="stop", pt=100, ct=20, tt=120, dur=800):
    return {"stage": "generation", "status": "ok", "duration_ms": dur,
            "detail": {"provider_id": provider, "model_id": model, "finish_reason": finish,
                       "prompt_tokens": pt, "completion_tokens": ct, "total_tokens": tt}}


def _item(created_at, span=None, extra_spans=None):
    spans = list(extra_spans or [])
    if span is not None:
        spans.append(span)
    return (created_at, {"spans": spans})


def _dt(h):
    return datetime(2026, 8, 1, h, 30, tzinfo=timezone.utc)


def test_generation_events_skips_missing_and_skipped():
    skipped = {"stage": "generation", "status": "skipped", "detail": None}
    other = {"stage": "intent", "status": "ok", "detail": {}}
    items = [_item(_dt(1), _gen_span()),
             _item(_dt(2), skipped),                 # skipped -> sayilmaz
             _item(_dt(3), None, extra_spans=[other])]  # generation yok -> sayilmaz
    evs = generation_events(items)
    assert len(evs) == 1
    assert evs[0]["model_id"] == "m1" and evs[0]["duration_ms"] == 800


def test_aggregate_by_model_cost_and_sort():
    price = {"m1": {"input_per_1m": 1000000.0, "output_per_1m": 0.0}}  # 1$/token in
    evs = [
        {"model_id": "m1", "provider_id": "p", "prompt_tokens": 2, "completion_tokens": 0, "total_tokens": 2},
        {"model_id": "m2", "provider_id": "p", "prompt_tokens": 5, "completion_tokens": 0, "total_tokens": 5},
    ]
    rows = aggregate_usage(evs, "model_id", price, ModelUsage)
    out = [r.to_payload() for r in rows]
    # total_tokens DESC -> m2(5) once; m2 fiyatsiz -> cost None; m1 fiyatli -> 2 token * 1$ = 2.0
    assert out[0]["model_id"] == "m2" and out[0]["estimated_cost"] is None
    assert out[1]["model_id"] == "m1" and out[1]["estimated_cost"] == 2.0


def test_aggregate_none_key_becomes_unknown():
    evs = [{"model_id": None, "provider_id": None, "prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}]
    rows = aggregate_usage(evs, "provider_id", {}, ProviderUsage)
    assert rows[0].provider_id == "unknown"


def test_latency_nearest_rank_and_none():
    evs = [{"duration_ms": d} for d in [10, 20, 30, 40]]
    ls = latency_stats(evs).to_payload()
    assert ls["count"] == 4 and ls["p50"] == 20 and ls["p95"] == 40 and ls["p99"] == 40
    empty = latency_stats([{"duration_ms": None}]).to_payload()
    assert empty == {"count": 0, "p50": None, "p95": None, "p99": None}


def test_finish_reason_counts_sorted_skip_none():
    evs = [{"finish_reason": "stop"}, {"finish_reason": "stop"},
           {"finish_reason": "length"}, {"finish_reason": None}]
    assert finish_reason_counts(evs) == {"stop": 2, "length": 1}


def test_bucket_timeseries_day_floor_cost_and_truncated():
    price = {"m1": {"input_per_1m": 1000000.0, "output_per_1m": 0.0}}
    evs = [{"created_at": _dt(10), "model_id": "m1", "prompt_tokens": 1, "completion_tokens": 0, "total_tokens": 5},
           {"created_at": _dt(14), "model_id": "m1", "prompt_tokens": 1, "completion_tokens": 0, "total_tokens": 7}]
    buckets, truncated = bucket_usage_timeseries(evs, "day", price)
    assert truncated is False and len(buckets) == 1
    b = buckets[0].to_payload()
    assert b["bucket_start"] == "2026-08-01T00:00:00+00:00"
    assert b["request_count"] == 2 and b["total_tokens"] == 12
    assert b["estimated_cost"] == 2.0  # 2 event * 1 prompt token * 1$


def test_bucket_timeseries_truncation_keeps_recent():
    from datetime import timedelta
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    evs = [{"created_at": base + timedelta(days=i), "model_id": "m", "prompt_tokens": 0,
            "completion_tokens": 0, "total_tokens": 1} for i in range(MAX_USAGE_BUCKETS + 5)]
    buckets, truncated = bucket_usage_timeseries(evs, "day", {})
    assert truncated is True and len(buckets) == MAX_USAGE_BUCKETS
    assert buckets[0].bucket_start > base.isoformat()


def test_bucket_timeseries_empty():
    assert bucket_usage_timeseries([], "day", {}) == ((), False)
