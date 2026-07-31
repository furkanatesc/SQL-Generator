from datetime import datetime, timezone
from app.llm_usage import compute_llm_usage, UsageWindow, LLM_USAGE_CONTRACT_VERSION


def _win(n):
    return UsageWindow(created_after=None, created_before=None, bucket="day",
                       trace_count=n, generation_count=0, truncated=False,
                       scan_cap=10000, timeseries_truncated=False)


def _gen(model, pt, ct, tt, provider="nvidia", finish="stop", dur=800):
    return {"stage": "generation", "status": "ok", "duration_ms": dur,
            "detail": {"provider_id": provider, "model_id": model, "finish_reason": finish,
                       "prompt_tokens": pt, "completion_tokens": ct, "total_tokens": tt}}


def _item(h, span):
    return (datetime(2026, 8, 1, h, tzinfo=timezone.utc), {"spans": [span]})


def _args():
    items = [_item(10, _gen("m1", 1_000_000, 0, 1_000_000)),
             _item(11, _gen("m2", 500_000, 0, 500_000))]
    price = {"m1": {"input_per_1m": 2.0, "output_per_1m": 0.0}}  # m2 fiyatsiz
    return dict(trace_items=items, window=_win(2), currency="USD",
                price_table=price, bucket="day")


def test_compute_builds_all_sections():
    p = compute_llm_usage(**_args()).to_payload()
    assert p["version"] == LLM_USAGE_CONTRACT_VERSION and p["currency"] == "USD"
    assert p["window"]["generation_count"] == 2
    assert p["totals"]["total_tokens"] == 1_500_000
    assert p["totals"]["request_count"] == 2
    assert p["totals"]["estimated_cost"] == 2.0        # m1: 1M*2/1e6=2.0 ; m2 fiyatsiz -> haric
    assert p["totals"]["unpriced_request_count"] == 1
    assert p["pricing"]["models_priced"] == ["m1"]
    assert p["pricing"]["models_missing_price"] == ["m2"]
    assert p["latency_ms"]["count"] == 2
    assert p["finish_reasons"] == {"stop": 2}
    assert p["timeseries"][0]["bucket_start"] == "2026-08-01T00:00:00+00:00"
    # m2 (fiyatsiz) cost None
    m2 = next(m for m in p["by_model"] if m["model_id"] == "m2")
    assert m2["estimated_cost"] is None


def test_compute_deterministic():
    assert compute_llm_usage(**_args()).to_payload() == compute_llm_usage(**_args()).to_payload()


def test_compute_empty_window():
    p = compute_llm_usage(trace_items=[], window=_win(0), currency="USD",
                          price_table={}, bucket="day").to_payload()
    assert p["window"]["generation_count"] == 0
    assert p["totals"] == {"request_count": 0, "prompt_tokens": 0, "completion_tokens": 0,
                           "total_tokens": 0, "estimated_cost": 0.0, "unpriced_request_count": 0}
    assert p["by_model"] == [] and p["by_provider"] == [] and p["timeseries"] == []
    assert p["finish_reasons"] == {} and p["latency_ms"]["count"] == 0
    assert p["pricing"] == {"models_priced": [], "models_missing_price": []}
