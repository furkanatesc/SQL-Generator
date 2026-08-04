from benchmarks.bench_runner import run_benchmark


def _fake_clock():
    counter = {"t": 0.0}

    def clock():
        counter["t"] += 0.001
        return counter["t"]
    return clock


def test_run_benchmark_deterministic_metrics():
    a = run_benchmark(scales=(30,), seed=7, clock=_fake_clock()).to_dict()
    b = run_benchmark(scales=(30,), seed=7, clock=_fake_clock()).to_dict()
    a_det = [(m["target"], m["scale"], m["deterministic"]) for m in a["metrics"]]
    b_det = [(m["target"], m["scale"], m["deterministic"]) for m in b["metrics"]]
    assert a_det == b_det


def test_run_benchmark_emits_four_targets_per_scale():
    # NOTE: v2 (Sprint 28.1) adds a fifth `graph_backend` target per scale;
    # this test's name is historical but its assertions now reflect 5 targets.
    report = run_benchmark(scales=(30, 40), seed=7, clock=_fake_clock()).to_dict()
    targets = [m["target"] for m in report["metrics"]]
    assert targets == [
        "schema_validation", "join_paths", "implicit_fk", "context_selection", "graph_backend",
        "schema_validation", "join_paths", "implicit_fk", "context_selection", "graph_backend",
    ]
    assert report["generator_params"]["seed"] == 7
    assert report["generator_params"]["scales"] == [30, 40]


def test_run_benchmark_metrics_have_expected_keys():
    report = run_benchmark(scales=(30,), seed=7, clock=_fake_clock()).to_dict()
    by_target = {m["target"]: m["deterministic"] for m in report["metrics"]}
    assert by_target["schema_validation"]["tables"] == 30
    assert "paths_found_total" in by_target["join_paths"]
    assert "implicit_rels_found" in by_target["implicit_fk"]
    assert "selected_tables_total" in by_target["context_selection"]


def test_runner_emits_probe_counters():
    report = run_benchmark(scales=(30,), seed=7, clock=_fake_clock()).to_dict()
    by_target = {m["target"]: m["deterministic"] for m in report["metrics"]}
    assert by_target["join_paths"].get("dfs_visit", 0) >= 1
    assert by_target["implicit_fk"].get("pair_iteration", 0) >= 1
    assert by_target["context_selection"].get("table_scan", 0) >= 1


def test_runner_emits_graph_backend_target():
    report = run_benchmark(scales=(30, 40), seed=7, clock=_fake_clock()).to_dict()
    targets = [m["target"] for m in report["metrics"]]
    assert targets == [
        "schema_validation", "join_paths", "implicit_fk", "context_selection", "graph_backend",
        "schema_validation", "join_paths", "implicit_fk", "context_selection", "graph_backend",
    ]
    gb = next(m for m in report["metrics"] if m["target"] == "graph_backend")
    assert gb["deterministic"]["graph_nodes"] == 30
    assert "sp_pairs_with_path" in gb["deterministic"]


def test_runner_params_include_density_and_hubs():
    report = run_benchmark(scales=(30,), seed=7, clock=_fake_clock()).to_dict()
    assert "fk_density" in report["generator_params"]
    assert "hub_count" in report["generator_params"]


def test_runner_deterministic_with_probes():
    a = run_benchmark(scales=(30,), seed=7, clock=_fake_clock()).to_dict()
    b = run_benchmark(scales=(30,), seed=7, clock=_fake_clock()).to_dict()
    a_det = [(m["target"], m["deterministic"]) for m in a["metrics"]]
    b_det = [(m["target"], m["deterministic"]) for m in b["metrics"]]
    assert a_det == b_det
