from app.metrics import compute_metrics, MetricsWindow, METRICS_CONTRACT_VERSION


def _w(n=0):
    return MetricsWindow(trace_count=n, scan_cap=10000)


def _trace(terminal, total_ms, spans):
    return {"version": "end_to_end_trace_v1", "terminal_status": terminal,
            "total_duration_ms": total_ms, "spans": spans}


def _span(stage, status, reason_code=None):
    attrs = {"reason_code": reason_code} if reason_code else {}
    return {"stage": stage, "status": status, "duration_ms": 1, "attributes": attrs}


def test_outcome_distribution_and_success_rate():
    payloads = [
        _trace("completed", 10, [_span("intent", "ok")]),
        _trace("completed", 20, [_span("intent", "ok")]),
        _trace("failed", 30, [_span("retrieval", "error", "schema_pruning_failed")]),
    ]
    r = compute_metrics(payloads, _w(3)).to_payload()
    assert r["outcome"]["total"] == 3
    assert r["outcome"]["terminal_status"] == {"completed": 2, "failed": 1}
    assert r["outcome"]["success_rate"] == 0.6667  # round(2/3,4)


def test_success_rate_null_when_empty():
    r = compute_metrics([], _w(0)).to_payload()
    assert r["outcome"]["total"] == 0
    assert r["outcome"]["success_rate"] is None
    assert r["latency_ms"] == {"count": 0, "p50": None, "p95": None, "p99": None,
                               "min": None, "max": None, "mean": None}
    assert r["errors"] == {"by_code": {}, "by_category": {}}


def test_errors_by_code_and_category_with_unknown_bucket():
    payloads = [
        _trace("failed", 5, [_span("retrieval", "error", "schema_pruning_failed")]),
        _trace("failed", 5, [_span("validation", "error", "missing_column")]),
        _trace("failed", 5, [_span("generation", "error", "not_a_real_code_xyz")]),
    ]
    r = compute_metrics(payloads, _w(3)).to_payload()
    assert r["errors"]["by_code"]["schema_pruning_failed"] == 1
    assert r["errors"]["by_code"]["not_a_real_code_xyz"] == 1
    # bilinmeyen kod "unknown" kovasina; bilinen kodlar 27.2 registry kategorisine
    assert r["errors"]["by_category"]["unknown"] == 1
    assert sum(r["errors"]["by_category"].values()) == 3


def test_latency_nearest_rank_percentiles():
    payloads = [_trace("completed", ms, [_span("intent", "ok")]) for ms in (40, 10, 30, 20)]
    lat = compute_metrics(payloads, _w(4)).to_payload()["latency_ms"]
    # sirali [10,20,30,40]; nearest-rank rank=ceil(p*n)
    assert lat["count"] == 4
    assert lat["min"] == 10 and lat["max"] == 40
    assert lat["p50"] == 20   # ceil(.5*4)=2 -> idx1
    assert lat["p95"] == 40   # ceil(.95*4)=4 -> idx3
    assert lat["p99"] == 40
    assert lat["mean"] == 25.0


def test_latency_skips_none_durations():
    payloads = [
        _trace("completed", None, [_span("intent", "ok")]),
        _trace("completed", 50, [_span("intent", "ok")]),
    ]
    lat = compute_metrics(payloads, _w(2)).to_payload()["latency_ms"]
    assert lat["count"] == 1 and lat["p50"] == 50


def test_stages_status_distribution():
    payloads = [
        _trace("completed", 10, [_span("intent", "ok"), _span("retrieval", "ok")]),
        _trace("failed", 10, [_span("intent", "ok"), _span("retrieval", "error", "schema_pruning_failed")]),
        _trace("completed", 10, [_span("intent", "ok"), _span("security", "skipped")]),
    ]
    stages = compute_metrics(payloads, _w(3)).to_payload()["stages"]
    assert stages["intent"] == {"ok": 3}
    assert stages["retrieval"] == {"error": 1, "ok": 1}
    assert stages["security"] == {"skipped": 1}


def test_report_is_deterministic():
    payloads = [_trace("completed", 10, [_span("intent", "ok")])]
    assert compute_metrics(payloads, _w(1)).to_payload() == compute_metrics(payloads, _w(1)).to_payload()
    assert compute_metrics(payloads, _w(1)).to_payload()["version"] == METRICS_CONTRACT_VERSION
