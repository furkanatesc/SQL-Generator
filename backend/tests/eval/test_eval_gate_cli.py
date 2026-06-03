import json
import pytest
from pathlib import Path
from evals.eval_gate import evaluate_release_gate
from evals.eval_gate_cli import main as gate_cli_main
from app.eval.run_eval import main as run_eval_main

def test_eval_gate_accepts_enriched_report():
    enriched_report = {
        "total": 2,
        "passed": 1,
        "failed": 1,
        "pass_rate": 0.5,
        "results": [
            {
                "id": "case_1",
                "expected_type": "success",
                "passed": False,
                "reason": "Missing columns",
                "actual": {"success": False, "generated_sql": "", "error_type": None, "stage": None},
                "checks": [{"name": "expected_columns", "passed": False, "message": "Missing columns", "details": {}}],
                "failed_checks": [{"name": "expected_columns", "message": "Missing columns", "details": {}}]
            }
        ],
        "failed_cases": [
            {
                "id": "case_1",
                "expected_type": "success",
                "reason": "Missing columns",
                "failed_checks": [{"name": "expected_columns", "message": "Missing columns", "details": {}}]
            }
        ]
    }
    
    result = evaluate_release_gate(enriched_report)
    assert result["gate_passed"] is False
    assert result["summary"]["failed"] == 1
    # Check that failed_cases metadata is preserved in the gate output
    assert len(result["failed_cases"]) == 1
    assert "failed_checks" in result["failed_cases"][0]

def test_eval_gate_fails_when_failed_exceeds_max():
    report = {
        "total": 5,
        "passed": 3,
        "failed": 2,
        "pass_rate": 0.6,
        "results": [],
        "failed_cases": []
    }
    
    # 1. max_failed = 0 -> fails
    result = evaluate_release_gate(report, policy={"max_failed": 0, "min_pass_rate": 0.0})
    assert result["gate_passed"] is False
    
    # 2. max_failed = 2 -> passes (since failed is 2, not > 2)
    result = evaluate_release_gate(report, policy={"max_failed": 2, "min_pass_rate": 0.0})
    assert result["gate_passed"] is True
    
    # 3. max_failed = 1 -> fails
    result = evaluate_release_gate(report, policy={"max_failed": 1, "min_pass_rate": 0.0})
    assert result["gate_passed"] is False

def test_eval_gate_fails_on_empty_report_when_require_non_empty():
    report = {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "pass_rate": 0.0,
        "results": [],
        "failed_cases": []
    }
    
    # Defaults to require_non_empty = True
    result = evaluate_release_gate(report)
    assert result["gate_passed"] is False
    assert result["reason"] == "No eval cases were run"
    
    # Override policy to not require non-empty
    result = evaluate_release_gate(report, policy={"require_non_empty": False, "min_pass_rate": 0.0})
    assert result["gate_passed"] is True

def test_cli_output_writes_enriched_report(tmp_path):
    report_file = tmp_path / "enriched_report.json"
    
    # We call run_eval main with --output option
    # Smoke profile contains 1 test case (smoke_list_customers), which passes cleanly in fake pipeline
    exit_code = run_eval_main(["--profile", "smoke", "--output", str(report_file)])
    assert exit_code == 0
    
    # Read the output file and check its schema
    assert report_file.exists()
    written_data = json.loads(report_file.read_text(encoding="utf-8"))
    
    assert "results" in written_data
    assert len(written_data["results"]) > 0
    
    # The result should contain "checks" and "failed_checks" lists
    res = written_data["results"][0]
    assert "checks" in res
    assert "failed_checks" in res
    assert isinstance(res["checks"], list)
    assert isinstance(res["failed_checks"], list)

def test_cli_json_option_does_not_regress(capsys):
    exit_code = run_eval_main(["--profile", "smoke", "--json"])
    assert exit_code == 0
    
    captured = capsys.readouterr()
    stdout_data = json.loads(captured.out)
    
    # Verify the structure matches suite_result_to_dict
    assert "profile" in stdout_data
    assert "summary" in stdout_data
    assert "results" in stdout_data
    
    # Check that it doesn't contain run_eval report root-level elements (like total, failed, failed_cases)
    assert "total" not in stdout_data
    assert "failed_cases" not in stdout_data
