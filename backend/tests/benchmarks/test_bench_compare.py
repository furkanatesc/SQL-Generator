# backend/tests/benchmarks/test_bench_compare.py
from benchmarks.bench_compare import compare_benchmark


def _report(metrics):
    return {"schema_version": "large_schema_benchmark_v1",
            "generator_params": {"seed": 1729},
            "metrics": metrics}


def _m(target, scale, det, wall=9.9):
    return {"target": target, "scale": scale, "deterministic": det, "wall_ms": wall}


def test_bootstrap_when_no_baseline():
    cur = _report([_m("join_paths", 100, {"paths_found_total": 5})])
    res = compare_benchmark(cur, None)
    assert res["gate_passed"] is True
    assert res["bootstrap"] is True
    assert res["mismatches"] == []


def test_exact_match_passes_ignoring_wall_ms():
    cur = _report([_m("join_paths", 100, {"paths_found_total": 5}, wall=1.0)])
    base = _report([_m("join_paths", 100, {"paths_found_total": 5}, wall=999.0)])
    res = compare_benchmark(cur, base)
    assert res["gate_passed"] is True
    assert res["mismatches"] == []


def test_metric_drift_fails_with_detail():
    cur = _report([_m("join_paths", 100, {"paths_found_total": 8})])
    base = _report([_m("join_paths", 100, {"paths_found_total": 5})])
    res = compare_benchmark(cur, base)
    assert res["gate_passed"] is False
    assert res["mismatches"] == [{"target": "join_paths", "scale": 100,
                                  "metric": "paths_found_total", "expected": 5, "actual": 8}]


def test_missing_pair_is_mismatch():
    cur = _report([_m("join_paths", 100, {"paths_found_total": 5})])
    base = _report([_m("join_paths", 100, {"paths_found_total": 5}),
                    _m("implicit_fk", 100, {"implicit_rels_found": 3})])
    res = compare_benchmark(cur, base)
    assert res["gate_passed"] is False
    assert any(mm["metric"] == "*" and mm["target"] == "implicit_fk" for mm in res["mismatches"])
