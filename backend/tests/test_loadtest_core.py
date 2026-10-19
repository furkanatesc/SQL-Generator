from loadtest.core import SCENARIOS, Result, evaluate, percentile, schedule, summarize


def test_percentile():
    assert percentile(list(range(1, 101)), 95) == 95
    assert percentile([], 50) == 0.0


def test_schedule_mixed_ratio_and_determinism():
    names = [s.name for s in schedule(SCENARIOS["mixed"], 32)]
    assert names == [s.name for s in schedule(SCENARIOS["mixed"], 32)]
    # each read spec has weight 3, each write spec weight 1 (3:1 per endpoint); 17-slot cycle
    from collections import Counter

    counts = Counter(s.name for s in schedule(SCENARIOS["mixed"], 34))
    assert {counts[n] for n in ("health", "ready", "jobs_list", "query_history", "workspaces_list")} == {6}
    assert {counts["workspace_create"], counts["job_create"]} == {2}


def test_summarize_counts_and_endpoints():
    rs = [Result("a", 200, 10.0, True), Result("a", 500, 30.0, False),
          Result("b", None, 20.0, False), Result("b", 201, 40.0, True)]
    s = summarize(rs, 2.0)
    assert s["requests"] == 4 and s["errors"] == 2 and s["error_rate"] == 0.5
    assert s["throughput_rps"] == 2.0
    assert s["latency_ms"]["max"] == 40.0
    assert s["status_counts"] == {"200": 1, "500": 1, "None": 1, "201": 1}
    assert s["endpoints"]["a"]["errors"] == 1 and s["endpoints"]["b"]["requests"] == 2
    assert "endpoints" not in s["endpoints"]["a"]


def test_summarize_empty_is_total_failure():
    assert summarize([], 1.0)["error_rate"] == 1.0


def test_evaluate():
    s = summarize([Result("a", 500, 5000.0, False)], 1.0)
    assert len(evaluate(s, 0.0, 2000.0)) == 2
    ok = summarize([Result("a", 200, 5.0, True)], 1.0)
    assert evaluate(ok, 0.0, 2000.0) == []
