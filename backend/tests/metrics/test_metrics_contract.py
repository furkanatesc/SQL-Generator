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


def test_error_metrics_keys_sorted_deterministic():
    # by_code ve by_category sirali serilenmeli (determinizm)
    # Multi-key, non-alphabetical insertion order'ı assert eder
    errors = ErrorMetrics(
        by_code={"zzz_code": 1, "aaa_code": 2, "mmm_code": 1},
        by_category={"security": 1, "internal": 1, "generation": 1}
    )
    p = errors.to_payload()
    assert list(p["by_code"].keys()) == ["aaa_code", "mmm_code", "zzz_code"]
    assert list(p["by_category"].keys()) == ["generation", "internal", "security"]


def test_metrics_report_with_unsorted_errors():
    # MetricsReport'un stages ve errors'ının sirali serilenmesi
    report = MetricsReport(
        version=METRICS_CONTRACT_VERSION,
        window=MetricsWindow(created_after="2026-01-01", created_before=None,
                             dialect="postgres", trace_count=1, truncated=False, scan_cap=10000),
        outcome=OutcomeMetrics(total=1, terminal_status={"failed": 1},
                               success_rate=0.0),
        errors=ErrorMetrics(by_code={"zzz": 1, "aaa": 2, "mmm": 1},
                            by_category={"zzzcat": 1, "aaacat": 1}),
        latency_ms=LatencyMetrics(count=1, p50=None, p95=None, p99=None, min=None, max=None, mean=None),
        stages={"zzzstage": {"zzz_status": 1, "aaa_status": 1}, "aaastage": {"ok": 1}},
    )
    p = report.to_payload()
    assert list(p["stages"].keys()) == ["aaastage", "zzzstage"]
    assert list(p["stages"]["zzzstage"].keys()) == ["aaa_status", "zzz_status"]
    assert list(p["errors"]["by_code"].keys()) == ["aaa", "mmm", "zzz"]
    assert list(p["errors"]["by_category"].keys()) == ["aaacat", "zzzcat"]
