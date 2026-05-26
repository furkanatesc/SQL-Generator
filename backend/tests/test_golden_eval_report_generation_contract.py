import json
import socket
import pytest
from app.eval.run_eval import main
from app.eval.dataset_resolver import get_cases_for_profile
from app.eval.profiles import EvalProfile
from evals.eval_gate import evaluate_release_gate


# 1. Writes report file successfully
def test_golden_eval_runner_writes_report_file(tmp_path):
    report_path = tmp_path / "golden_eval_report.json"

    exit_code = main([
        "--profile", "golden",
        "--json",
        "--output", str(report_path),
    ])

    assert exit_code == 0
    assert report_path.exists()

    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert set(report.keys()) == {
        "total",
        "passed",
        "failed",
        "pass_rate",
        "results",
        "failed_cases",
    }


# 2. Matches the stable evaluation report schema (PR 9.4)
def test_golden_eval_report_matches_stable_schema(tmp_path):
    report_path = tmp_path / "golden_eval_report.json"

    exit_code = main([
        "--profile", "golden",
        "--json",
        "--output", str(report_path),
    ])

    assert exit_code == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))

    # Top-level keys and types
    assert isinstance(report["total"], int)
    assert isinstance(report["passed"], int)
    assert isinstance(report["failed"], int)
    assert isinstance(report["pass_rate"], float)
    assert isinstance(report["results"], list)
    assert isinstance(report["failed_cases"], list)

    # Detailed results schema
    for res in report["results"]:
        assert isinstance(res["id"], str)
        assert isinstance(res["expected_type"], str)
        assert isinstance(res["passed"], bool)
        assert res["reason"] is None or isinstance(res["reason"], str)
        assert isinstance(res["actual"], dict)

        actual = res["actual"]
        assert isinstance(actual["success"], bool)
        assert isinstance(actual["generated_sql"], str)
        assert actual["error_type"] is None or isinstance(actual["error_type"], str)
        assert actual["stage"] is None or isinstance(actual["stage"], str)

    # Detailed failed_cases schema
    for fc in report["failed_cases"]:
        assert isinstance(fc["id"], str)
        assert isinstance(fc["expected_type"], str)
        assert isinstance(fc["reason"], str)


# 3. Golden report is non-empty (total >= 5)
def test_golden_eval_report_is_non_empty(tmp_path):
    report_path = tmp_path / "golden_eval_report.json"

    exit_code = main([
        "--profile", "golden",
        "--json",
        "--output", str(report_path),
    ])

    assert exit_code == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["total"] >= 5


# 4. Total count matches golden profile case count exactly
def test_golden_eval_report_total_matches_golden_profile_case_count(tmp_path):
    report_path = tmp_path / "golden_eval_report.json"

    exit_code = main([
        "--profile", "golden",
        "--json",
        "--output", str(report_path),
    ])

    assert exit_code == 0

    report = json.loads(report_path.read_text(encoding="utf-8"))
    cases = get_cases_for_profile(EvalProfile.GOLDEN)

    assert report["total"] == len(cases)


# 5. All cases pass when evaluated with the fake pipeline
def test_golden_eval_report_all_cases_pass_with_fake_pipeline(tmp_path):
    report_path = tmp_path / "golden_eval_report.json"

    exit_code = main([
        "--profile", "golden",
        "--json",
        "--output", str(report_path),
    ])

    assert exit_code == 0

    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["passed"] == report["total"]
    assert report["failed"] == 0


# 6. Pass rate must be exactly 1.0 (since all pass with fake pipeline)
def test_golden_eval_report_pass_rate_is_one(tmp_path):
    report_path = tmp_path / "golden_eval_report.json"

    exit_code = main([
        "--profile", "golden",
        "--json",
        "--output", str(report_path),
    ])

    assert exit_code == 0

    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["pass_rate"] == 1.0


# 7. Failed cases list must be empty
def test_golden_eval_report_failed_cases_empty(tmp_path):
    report_path = tmp_path / "golden_eval_report.json"

    exit_code = main([
        "--profile", "golden",
        "--json",
        "--output", str(report_path),
    ])

    assert exit_code == 0

    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert report["failed_cases"] == []


# 8. Report passes the default release gate policy
def test_golden_eval_report_passes_default_release_gate(tmp_path):
    report_path = tmp_path / "golden_eval_report.json"

    exit_code = main([
        "--profile", "golden",
        "--json",
        "--output", str(report_path),
    ])

    assert exit_code == 0

    report = json.loads(report_path.read_text(encoding="utf-8"))
    gate_result = evaluate_release_gate(report)

    assert gate_result["gate_passed"] is True
    assert gate_result["reason"] is None


# 9. Rapor is fully JSON serializable
def test_golden_eval_report_is_json_serializable(tmp_path):
    report_path = tmp_path / "golden_eval_report.json"

    exit_code = main([
        "--profile", "golden",
        "--json",
        "--output", str(report_path),
    ])

    assert exit_code == 0

    report = json.loads(report_path.read_text(encoding="utf-8"))
    # Verifies that it can be dumped to standard JSON without any TypeError
    dumped = json.dumps(report)
    assert isinstance(dumped, str)


# 10. Report output is 100% deterministic (sorted and identical across repeated runs)
def test_golden_eval_report_is_deterministic_across_repeated_runs(tmp_path):
    path1 = tmp_path / "golden_report_1.json"
    path2 = tmp_path / "golden_report_2.json"

    main(["--profile", "golden", "--json", "--output", str(path1)])
    main(["--profile", "golden", "--json", "--output", str(path2)])

    assert path1.read_text(encoding="utf-8") == path2.read_text(encoding="utf-8")


# 11. Report does not include nondeterministic metadata (timestamps, environments, or execution times)
def test_golden_eval_report_does_not_include_nondeterministic_metadata(tmp_path):
    report_path = tmp_path / "golden_eval_report.json"

    exit_code = main([
        "--profile", "golden",
        "--json",
        "--output", str(report_path),
    ])

    assert exit_code == 0
    report = json.loads(report_path.read_text(encoding="utf-8"))

    # Recurse and assert no volatile keywords are present as keys in the dict
    def assert_no_volatile_keys(data):
        volatile_keywords = {
            "timestamp", "created_at", "run_at", "datetime", "time", 
            "duration", "elapsed", "speed", "env", "os", 
            "python_version", "system", "host", "user", "git_commit", "branch"
        }
        if isinstance(data, dict):
            for k, v in data.items():
                assert k.lower() not in volatile_keywords, f"Volatile/Non-deterministic key '{k}' found in report!"
                assert_no_volatile_keys(v)
        elif isinstance(data, list):
            for item in data:
                assert_no_volatile_keys(item)

    assert_no_volatile_keys(report)


# 12. Does not require database connection, LLM provider, or network calls
def test_golden_eval_report_does_not_require_db_llm_or_network(tmp_path, monkeypatch):
    # Guard against any socket or network communication
    def network_guard(*args, **kwargs):
        raise RuntimeError("External network connection or database connection was attempted in test!")

    monkeypatch.setattr(socket, "socket", network_guard)

    report_path = tmp_path / "golden_eval_report.json"

    exit_code = main([
        "--profile", "golden",
        "--json",
        "--output", str(report_path),
    ])

    assert exit_code == 0
    assert report_path.exists()
