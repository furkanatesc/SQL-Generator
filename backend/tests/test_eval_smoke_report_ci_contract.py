import json
from pathlib import Path
from app.eval.run_eval import main
from evals.eval_gate import evaluate_release_gate


# 1. Verify that the runner writes the report file successfully
def test_eval_smoke_runner_writes_report_file(tmp_path):
    report_path = tmp_path / "eval_smoke_report.json"

    exit_code = main([
        "--profile", "smoke",
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


# 2. Verify that the generated report matches the required PR 9.4/9.5 schema
def test_eval_smoke_runner_report_matches_eval_report_schema(tmp_path):
    report_path = tmp_path / "eval_smoke_report.json"
    main(["--profile", "smoke", "--output", str(report_path)])
    
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert isinstance(report["total"], int)
    assert isinstance(report["passed"], int)
    assert isinstance(report["failed"], int)
    assert isinstance(report["pass_rate"], float)
    assert isinstance(report["results"], list)
    assert isinstance(report["failed_cases"], list)
    
    for r in report["results"]:
        assert set(r.keys()) == {"id", "expected_type", "passed", "reason", "actual", "checks", "failed_checks"}
        assert isinstance(r["id"], str)
        assert isinstance(r["expected_type"], str)
        assert isinstance(r["passed"], bool)
        assert r["reason"] is None or isinstance(r["reason"], str)
        assert isinstance(r["actual"], dict)
        assert set(r["actual"].keys()) == {"success", "generated_sql", "error_type", "stage"}
        
    for f in report["failed_cases"]:
        assert set(f.keys()) == {"id", "expected_type", "reason", "failed_checks"}


# 3. Verify that the smoke evaluation report is non-empty
def test_eval_smoke_runner_report_is_non_empty(tmp_path):
    report_path = tmp_path / "eval_smoke_report.json"
    main(["--profile", "smoke", "--output", str(report_path)])
    
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["total"] > 0


# 4. Verify that the generated smoke report successfully passes the release gate
def test_eval_smoke_runner_report_passes_default_gate(tmp_path):
    report_path = tmp_path / "eval_smoke_report.json"
    main(["--profile", "smoke", "--output", str(report_path)])
    
    report = json.loads(report_path.read_text(encoding="utf-8"))
    gate_result = evaluate_release_gate(report)
    
    assert gate_result["gate_passed"] is True
    assert gate_result["reason"] is None


# 5. Verify that the generated smoke report is JSON-serializable
def test_eval_smoke_runner_report_is_json_serializable(tmp_path):
    report_path = tmp_path / "eval_smoke_report.json"
    main(["--profile", "smoke", "--output", str(report_path)])
    
    report = json.loads(report_path.read_text(encoding="utf-8"))
    serialized = json.dumps(report)
    parsed = json.loads(serialized)
    assert parsed == report


# 6. Verify that the generated smoke report is 100% deterministic across repeated runs
def test_eval_smoke_runner_output_is_deterministic_across_repeated_runs(tmp_path):
    path1 = tmp_path / "report1.json"
    path2 = tmp_path / "report2.json"
    
    main(["--profile", "smoke", "--output", str(path1)])
    main(["--profile", "smoke", "--output", str(path2)])
    
    assert path1.read_text(encoding="utf-8") == path2.read_text(encoding="utf-8")


# 7. Verify that the backend-ci.yml workflow generates the smoke report before gate
def test_backend_ci_generates_eval_smoke_report_before_gate():
    workflow_path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "backend-ci.yml"
    content = workflow_path.read_text(encoding="utf-8")
    
    assert "python -m app.eval.run_eval --profile smoke --json --output /tmp/eval_smoke_report.json" in content


# 8. Verify that the backend-ci.yml workflow runs the gate CLI on the generated smoke report
def test_backend_ci_runs_gate_cli_on_generated_report():
    workflow_path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "backend-ci.yml"
    content = workflow_path.read_text(encoding="utf-8")
    
    assert "python -m evals.eval_gate_cli /tmp/eval_smoke_report.json" in content


# 9. Verify that backend-ci.yml no longer uses static inline pass reports
def test_backend_ci_no_longer_uses_static_inline_pass_report():
    workflow_path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "backend-ci.yml"
    content = workflow_path.read_text(encoding="utf-8")
    
    assert "cat > /tmp/eval_report_pass.json" not in content
    assert "eval_report_pass.json" not in content


# 10. Verify that the new workflow steps do not use any secrets or network configurations
def test_backend_ci_eval_smoke_report_step_does_not_use_secrets_or_network():
    workflow_path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "backend-ci.yml"
    content = workflow_path.read_text(encoding="utf-8")
    
    steps = ["Run eval smoke profile and write report", "Run eval gate CLI on generated smoke report"]
    for step in steps:
        step_lines = []
        lines = content.splitlines()
        in_step = False
        for line in lines:
            if f"name: {step}" in line:
                in_step = True
            elif in_step and line.strip().startswith("- name:"):
                break
            elif in_step:
                step_lines.append(line)
                
        block = "\n".join(step_lines)
        assert "secrets." not in block
        assert "env:" not in block
