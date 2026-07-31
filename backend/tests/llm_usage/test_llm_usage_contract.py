import json
from app.llm_usage import (
    LLM_USAGE_CONTRACT_VERSION, LLMUsageReport, UsageWindow, UsageTotals,
    ModelUsage, ProviderUsage, LatencyStats, UsageBucket, PricingInfo,
)


def _sample() -> LLMUsageReport:
    return LLMUsageReport(
        version=LLM_USAGE_CONTRACT_VERSION,
        currency="USD",
        window=UsageWindow(created_after=None, created_before=None, bucket="day",
                           trace_count=3, generation_count=2, truncated=False,
                           scan_cap=10000, timeseries_truncated=False),
        totals=UsageTotals(request_count=2, prompt_tokens=5000, completion_tokens=1200,
                           total_tokens=6200, estimated_cost=0.0186, unpriced_request_count=0),
        by_model=(ModelUsage(model_id="m1", request_count=2, prompt_tokens=5000,
                             completion_tokens=1200, total_tokens=6200, estimated_cost=0.0186),),
        by_provider=(ProviderUsage(provider_id="nvidia", request_count=2, prompt_tokens=5000,
                                   completion_tokens=1200, total_tokens=6200, estimated_cost=0.0186),),
        latency_ms=LatencyStats(count=2, p50=820, p95=1400, p99=1600),
        finish_reasons={"stop": 1, "length": 1},
        timeseries=(UsageBucket(bucket_start="2026-08-01T00:00:00+00:00", request_count=2,
                                total_tokens=6200, estimated_cost=0.0186),),
        pricing=PricingInfo(models_priced=("m1",), models_missing_price=()),
    )


def test_to_payload_json_safe_and_shaped():
    p = _sample().to_payload()
    json.dumps(p)
    assert p["version"] == "llm_usage_v1"
    assert p["currency"] == "USD"
    assert set(p.keys()) == {"version", "currency", "window", "totals", "by_model",
                             "by_provider", "latency_ms", "finish_reasons",
                             "timeseries", "pricing"}
    assert p["totals"]["total_tokens"] == 6200
    assert p["by_model"][0]["model_id"] == "m1"
    assert p["latency_ms"]["p95"] == 1400
    assert p["timeseries"][0]["estimated_cost"] == 0.0186
    assert p["pricing"]["models_priced"] == ["m1"]


def test_finish_reasons_sorted_deterministic():
    p = _sample().to_payload()
    assert list(p["finish_reasons"].keys()) == ["length", "stop"]


def test_optional_cost_none_and_empty_sections():
    r = LLMUsageReport(
        version=LLM_USAGE_CONTRACT_VERSION, currency="USD",
        window=UsageWindow(None, None, "day", 0, 0, False, 10000, False),
        totals=UsageTotals(0, 0, 0, 0, 0.0, 0),
        by_model=(ModelUsage(model_id="m2", request_count=1, prompt_tokens=10,
                             completion_tokens=0, total_tokens=10, estimated_cost=None),),
        by_provider=(), latency_ms=LatencyStats(count=0, p50=None, p95=None, p99=None),
        finish_reasons={}, timeseries=(),
        pricing=PricingInfo(models_priced=(), models_missing_price=("m2",)))
    p = r.to_payload()
    assert p["by_model"][0]["estimated_cost"] is None
    assert p["by_provider"] == [] and p["timeseries"] == []
    assert p["latency_ms"] == {"count": 0, "p50": None, "p95": None, "p99": None}
    assert p["finish_reasons"] == {}
    assert p["pricing"]["models_missing_price"] == ["m2"]
