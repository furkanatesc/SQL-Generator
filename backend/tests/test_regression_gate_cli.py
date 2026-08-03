import json
from pathlib import Path

from evals.regression_gate_cli import main


def _write_report(path, cases):
    results = [{"id": cid, "passed": ok} for cid, ok in cases]
    passed = sum(1 for _, ok in cases if ok)
    total = len(cases)
    report = {"total": total, "passed": passed, "failed": total - passed,
              "pass_rate": (passed / total) if total else 0.0,
              "results": results, "failed_cases": []}
    Path(path).write_text(json.dumps(report), encoding="utf-8")


def _seed_history(path, version, case_ids, passing_ids):
    entry = {"version": version, "timestamp": "2026-08-03T00:00:00Z",
             "total": len(case_ids), "pass_rate": len(passing_ids) / len(case_ids),
             "case_ids": sorted(case_ids), "passing_case_ids": sorted(passing_ids)}
    Path(path).write_text(json.dumps([entry]), encoding="utf-8")


def test_gate_pass_returns_0(tmp_path, capsys):
    report = tmp_path / "r.json"
    hist = tmp_path / "history.json"
    _write_report(report, [("a", True), ("b", True)])
    _seed_history(hist, "v1.0.0", ["a", "b"], ["a", "b"])
    rc = main([str(report), "--baseline", str(hist)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["gate_passed"] is True


def test_gate_regression_returns_1(tmp_path, capsys):
    report = tmp_path / "r.json"
    hist = tmp_path / "history.json"
    _write_report(report, [("a", True), ("b", False)])
    _seed_history(hist, "v1.0.0", ["a", "b"], ["a", "b"])
    rc = main([str(report), "--baseline", str(hist)])
    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert out["newly_failing"] == ["b"]


def test_bootstrap_when_history_missing_returns_0(tmp_path, capsys):
    report = tmp_path / "r.json"
    hist = tmp_path / "history.json"   # yok
    _write_report(report, [("a", False)])
    rc = main([str(report), "--baseline", str(hist)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["bootstrap"] is True


def test_bad_report_returns_2(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{ not json", encoding="utf-8")
    assert main([str(bad), "--baseline", str(tmp_path / "h.json")]) == 2


def test_malformed_results_entry_returns_2(tmp_path):
    bad = tmp_path / "r.json"
    # results girdisi 'passed' alani eksik -> bad-input (2), regresyon (1) DEGIL
    bad.write_text(json.dumps({
        "total": 1, "passed": 1, "failed": 0, "pass_rate": 1.0,
        "results": [{"id": "a"}], "failed_cases": []}), encoding="utf-8")
    assert main([str(bad), "--baseline", str(tmp_path / "h.json")]) == 2


def test_missing_report_returns_2(tmp_path):
    assert main([str(tmp_path / "nope.json")]) == 2


def test_update_baseline_appends(tmp_path, capsys):
    report = tmp_path / "r.json"
    hist = tmp_path / "history.json"
    _write_report(report, [("a", True), ("b", True)])
    _seed_history(hist, "v1.0.0", ["a", "b"], ["a", "b"])
    rc = main([str(report), "--baseline", str(hist),
               "--update-baseline", "--version", "v1.1.0",
               "--timestamp", "2026-08-03T00:00:00Z"])
    assert rc == 0
    data = json.loads(hist.read_text(encoding="utf-8"))
    assert [e["version"] for e in data] == ["v1.0.0", "v1.1.0"]


def test_update_baseline_requires_version(tmp_path):
    report = tmp_path / "r.json"
    baseline = tmp_path / "h.json"
    _write_report(report, [("a", True)])
    rc = main([str(report), "--baseline", str(baseline),
               "--update-baseline"])
    assert rc == 2
    # Hata sonrasi baseline dosyasi olusturulmamis olmali
    assert not baseline.exists()


def test_update_baseline_duplicate_version_returns_2(tmp_path):
    report = tmp_path / "r.json"
    hist = tmp_path / "history.json"
    _write_report(report, [("a", True)])
    _seed_history(hist, "v1.0.0", ["a"], ["a"])
    # Hata oncesi history'nin baytlari
    before = hist.read_text(encoding="utf-8")
    rc = main([str(report), "--baseline", str(hist),
               "--update-baseline", "--version", "v1.0.0",
               "--timestamp", "2026-08-03T00:00:00Z"])
    assert rc == 2
    # Hata sonrasi history degismemis olmali
    assert hist.read_text(encoding="utf-8") == before


def test_max_pass_rate_drop_flag_parsed(tmp_path, capsys):
    report = tmp_path / "r.json"
    hist = tmp_path / "history.json"
    _write_report(report, [("a", True), ("b", True)])
    _seed_history(hist, "v1.0.0", ["a", "b"], ["a", "b"])
    rc = main([str(report), "--baseline", str(hist), "--max-pass-rate-drop", "0.1"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["aggregate"]["tolerance"] == 0.1
