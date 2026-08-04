from benchmarks.bench_contract import (
    BENCHMARK_SCHEMA_VERSION, BenchmarkMetric, BenchmarkReport,
)


def test_metric_to_dict_sorts_deterministic_keys():
    m = BenchmarkMetric(
        target="join_paths", scale=100,
        deterministic={"paths_found_total": 5, "adjacency_edges": 3},
        wall_ms=1.23,
    )
    d = m.to_dict()
    assert d == {
        "target": "join_paths",
        "scale": 100,
        "deterministic": {"adjacency_edges": 3, "paths_found_total": 5},
        "wall_ms": 1.23,
    }
    assert list(d["deterministic"].keys()) == ["adjacency_edges", "paths_found_total"]


def test_report_to_dict_stable_and_orders_metrics():
    report = BenchmarkReport(
        schema_version=BENCHMARK_SCHEMA_VERSION,
        generator_params={"seed": 1729, "dialect": "postgres"},
        metrics=(
            BenchmarkMetric("schema_validation", 100, {"tables": 100}, 0.5),
            BenchmarkMetric("join_paths", 100, {"paths_found_total": 2}, 0.7),
        ),
    )
    d = report.to_dict()
    assert d["schema_version"] == "large_schema_benchmark_v1"
    assert list(d["generator_params"].keys()) == ["dialect", "seed"]
    assert [m["target"] for m in d["metrics"]] == ["schema_validation", "join_paths"]
