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
    report = run_benchmark(scales=(30, 40), seed=7, clock=_fake_clock()).to_dict()
    targets = [m["target"] for m in report["metrics"]]
    assert targets == [
        "schema_validation", "join_paths", "implicit_fk", "context_selection",
        "schema_validation", "join_paths", "implicit_fk", "context_selection",
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
