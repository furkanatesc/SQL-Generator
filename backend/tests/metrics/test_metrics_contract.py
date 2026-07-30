import json
from app.metrics import (
    METRICS_CONTRACT_VERSION, MetricsReport, MetricsWindow,
    OutcomeMetrics, ErrorMetrics, LatencyMetrics,
)


def _sample() -> MetricsReport:
    return MetricsReport(
        version=METRICS_CONTRACT_VERSION,
        window=MetricsWindow(created_after="2026-01-01", created_before=None,
                             dialect="postgres", trace_count=3, truncated=False, scan_cap=10000),
        outcome=OutcomeMetrics(total=3, terminal_status={"failed": 1, "completed": 2},
                               success_rate=0.6667),
        errors=ErrorMetrics(by_code={"schema_pruning_failed": 1},
                            by_category={"retrieval": 1}),
        latency_ms=LatencyMetrics(count=3, p50=20, p95=40, p99=40, min=10, max=40, mean=23.33),
        stages={"retrieval": {"error": 1, "ok": 2}, "intent": {"ok": 3}},
    )


def test_to_payload_json_safe_and_shaped():
    p = _sample().to_payload()
    json.dumps(p)
    assert p["version"] == "metrics_v1"
    assert set(p.keys()) == {"version", "window", "outcome", "errors", "latency_ms", "stages"}
    assert p["outcome"]["success_rate"] == 0.6667
    assert p["window"]["truncated"] is False


def test_dict_keys_sorted_deterministic():
    p = _sample().to_payload()
    # terminal_status ve stages anahtarlari sirali serilenmeli (determinizm)
    assert list(p["outcome"]["terminal_status"].keys()) == ["completed", "failed"]
    assert list(p["stages"].keys()) == ["intent", "retrieval"]
    assert list(p["stages"]["retrieval"].keys()) == ["error", "ok"]
    assert _sample().to_payload() == _sample().to_payload()


def test_empty_latency_serializes_none():
    lm = LatencyMetrics(count=0, p50=None, p95=None, p99=None, min=None, max=None, mean=None)
    assert lm.to_payload() == {"count": 0, "p50": None, "p95": None, "p99": None,
                               "min": None, "max": None, "mean": None}
