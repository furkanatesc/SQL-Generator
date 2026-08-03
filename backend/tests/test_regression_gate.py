from evals.regression_gate import compare_regression, DEFAULT_REGRESSION_POLICY


def _report(cases):
    # cases: [(id, passed), ...]
    results = [{"id": cid, "passed": ok} for cid, ok in cases]
    passed = sum(1 for _, ok in cases if ok)
    total = len(cases)
    return {"total": total, "passed": passed, "failed": total - passed,
            "pass_rate": (passed / total) if total else 0.0,
            "results": results, "failed_cases": []}


def _baseline(version, case_ids, passing_ids, pass_rate):
    return {"version": version, "timestamp": "2026-08-03T00:00:00Z",
            "total": len(case_ids), "pass_rate": pass_rate,
            "case_ids": sorted(case_ids), "passing_case_ids": sorted(passing_ids)}


def test_clean_pass_no_regression():
    base = _baseline("v1.0.0", ["a", "b", "c", "d"], ["a", "b", "c", "d"], 1.0)
    cur = _report([("a", True), ("b", True), ("c", True), ("d", True)])
    r = compare_regression(cur, base)
    assert r["gate_passed"] is True
    assert r["bootstrap"] is False
    assert r["reason"] is None
    assert r["newly_failing"] == []
    assert r["baseline_version"] == "v1.0.0"


def test_per_case_newly_failing_is_regression():
    base = _baseline("v1.0.0", ["a", "b", "c", "d"], ["a", "b", "c", "d"], 1.0)
    cur = _report([("a", True), ("b", False), ("c", True), ("d", True)])
    r = compare_regression(cur, base)
    assert r["gate_passed"] is False
    assert r["reason"] == "Previously-passing cases now failing"
    assert r["newly_failing"] == ["b"]


def test_intersection_scope_removed_and_new_do_not_trip():
    # baseline gecen: a,b,c,d ; current: a,b,c (d removed) + e (new, failing)
    base = _baseline("v1.0.0", ["a", "b", "c", "d"], ["a", "b", "c", "d"], 1.0)
    cur = _report([("a", True), ("b", True), ("c", True), ("e", False)])
    r = compare_regression(cur, base)
    assert r["gate_passed"] is True            # d removed, e new -> kapiyi patlatmaz
    assert r["new_cases"] == ["e"]
    assert r["removed_cases"] == ["d"]
    assert r["newly_failing"] == []


def test_newly_passing_is_informational():
    base = _baseline("v1.0.0", ["a", "b"], ["a"], 0.5)   # b baseline'da DUSUK
    cur = _report([("a", True), ("b", True)])            # b simdi geciyor
    r = compare_regression(cur, base)
    assert r["gate_passed"] is True
    assert r["newly_passing"] == ["b"]
    assert r["newly_failing"] == []


def test_aggregate_drop_reported_and_per_case_priority():
    # common-kapsamda aggregate ancak bir baseline-passing case duserse duser,
    # bu da per-case'i zaten tetikler (spec §5.1 ortusme notu). Bu test hem
    # drop'un dogru hesaplandigini hem reason onceliginin per-case oldugunu dogrular.
    base = _baseline("v1.0.0", ["a", "b", "c", "d"], ["a", "b", "c", "d"], 1.0)
    cur = _report([("a", True), ("b", False), ("c", True), ("d", True)])
    r = compare_regression(cur, base, policy={"max_pass_rate_drop": 0.5})
    assert r["reason"] == "Previously-passing cases now failing"   # per-case oncelik
    assert r["aggregate"]["drop"] == 0.25                          # 1/4, tam hesap
    assert r["aggregate"]["tolerance"] == 0.5


def test_bootstrap_when_no_baseline():
    cur = _report([("a", True), ("b", False)])
    r = compare_regression(cur, None)
    assert r["gate_passed"] is True
    assert r["bootstrap"] is True
    assert r["reason"] == "No baseline recorded yet (bootstrap)"
    assert r["baseline_version"] is None
    assert r["new_cases"] == ["a", "b"]


def test_deterministic_same_input_same_output():
    base = _baseline("v1.0.0", ["a", "b"], ["a", "b"], 1.0)
    cur = _report([("a", True), ("b", True)])
    assert compare_regression(cur, base) == compare_regression(cur, base)


def test_default_policy_shape():
    assert DEFAULT_REGRESSION_POLICY == {"max_pass_rate_drop": 0.0}


import pytest
from evals.regression_gate import (
    build_baseline_entry, select_latest_baseline, append_baseline,
)


def test_build_baseline_entry_sorted_and_split():
    report = _report([("b", True), ("a", True), ("c", False)])
    entry = build_baseline_entry(report, version="v1.2.0", timestamp="2026-08-03T00:00:00Z")
    assert entry["version"] == "v1.2.0"
    assert entry["timestamp"] == "2026-08-03T00:00:00Z"
    assert entry["total"] == 3
    assert entry["case_ids"] == ["a", "b", "c"]          # SIRALI, tumu
    assert entry["passing_case_ids"] == ["a", "b"]        # SIRALI, gecen alt-kume
    assert entry["pass_rate"] == report["pass_rate"]


def test_select_latest_baseline():
    assert select_latest_baseline([]) is None
    h = [{"version": "v1.0.0"}, {"version": "v1.1.0"}]
    assert select_latest_baseline(h)["version"] == "v1.1.0"


def test_append_baseline_appends_new():
    entry = build_baseline_entry(_report([("a", True)]), version="v1.0.0",
                                 timestamp="2026-08-03T00:00:00Z")
    h2 = append_baseline([], entry)
    assert len(h2) == 1 and h2[0]["version"] == "v1.0.0"


def test_append_baseline_rejects_duplicate_version():
    e1 = build_baseline_entry(_report([("a", True)]), version="v1.0.0",
                              timestamp="2026-08-03T00:00:00Z")
    with pytest.raises(ValueError):
        append_baseline([e1], e1)


def test_append_baseline_does_not_mutate_input():
    e1 = build_baseline_entry(_report([("a", True)]), version="v1.0.0",
                              timestamp="2026-08-03T00:00:00Z")
    e2 = build_baseline_entry(_report([("a", True)]), version="v1.1.0",
                              timestamp="2026-08-03T00:00:00Z")
    original = [e1]
    append_baseline(original, e2)
    assert original == [e1]      # girdi degismedi
