import json
from pathlib import Path
from evals.eval_gate_cli import main


# 1. Verify that .github/workflows/backend-ci.yml runs the eval gate CLI smoke step
def test_backend_ci_runs_eval_gate_cli_smoke_step():
    workflow_path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "backend-ci.yml"
    content = workflow_path.read_text(encoding="utf-8")
    
    assert "python -m evals.eval_gate_cli" in content
    assert "eval_report_pass.json" in content


# 2. Verify that the CI smoke report structure is a passing report
def test_backend_ci_eval_gate_smoke_uses_passing_report():
    workflow_path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "backend-ci.yml"
    content = workflow_path.read_text(encoding="utf-8")

    assert '"total": 1' in content
    assert '"passed": 1' in content
    assert '"failed": 0' in content
    assert '"pass_rate": 1.0' in content


# 3. Verify that the CI smoke report does not use failing parameters
def test_backend_ci_eval_gate_smoke_does_not_use_failure_report():
    workflow_path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "backend-ci.yml"
    content = workflow_path.read_text(encoding="utf-8")

    assert '"failed": 1' not in content
    assert '"passed": 0' not in content
    assert '"pass_rate": 0.' not in content


# 4. Verify that the smoke step does not require secrets, environment variables, or network
def test_backend_ci_eval_gate_smoke_does_not_use_network_or_secrets():
    workflow_path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "backend-ci.yml"
    content = workflow_path.read_text(encoding="utf-8")

    smoke_step_lines = []
    lines = content.splitlines()
    in_smoke_step = False
    for line in lines:
        if "name: Run eval gate CLI smoke" in line:
            in_smoke_step = True
        elif in_smoke_step and line.strip().startswith("- name:"):
            break
        elif in_smoke_step:
            smoke_step_lines.append(line)
            
    smoke_block = "\n".join(smoke_step_lines)
    assert "secrets." not in smoke_block
    assert "env:" not in smoke_block


# 5. Verify that the exact pass report structure used in CI still returns exit code 0 when ran locally
def test_eval_gate_cli_contract_still_returns_zero_for_ci_pass_report(tmp_path, capsys):
    report_path = tmp_path / "eval_report_pass.json"
    report_path.write_text(json.dumps({
        "total": 1,
        "passed": 1,
        "failed": 0,
        "pass_rate": 1.0,
        "results": [],
        "failed_cases": []
    }), encoding="utf-8")

    exit_code = main([str(report_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""
    
    output = json.loads(captured.out)
    assert output["gate_passed"] is True
