import json
import re
from pathlib import Path
from app.eval.run_eval import main
from evals.eval_gate import evaluate_release_gate


# 1. Verifies that the workflow file contains the golden eval report generation command
def test_backend_ci_generates_golden_eval_report():
    workflow = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "backend-ci.yml"
    content = workflow.read_text(encoding="utf-8")

    assert "python -m app.eval.run_eval --profile golden --json --output /tmp/golden_eval_report.json" in content


# 2. Verifies that the workflow file contains the gate CLI invocation using the generated report
def test_backend_ci_runs_gate_cli_on_generated_golden_report():
    workflow = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "backend-ci.yml"
    content = workflow.read_text(encoding="utf-8")

    assert "python -m evals.eval_gate_cli /tmp/golden_eval_report.json" in content


# 3. Verifies that the report generation happens BEFORE the gate CLI execution
def test_backend_ci_generates_golden_report_before_gate():
    workflow = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "backend-ci.yml"
    content = workflow.read_text(encoding="utf-8")

    generate_cmd = "python -m app.eval.run_eval --profile golden --json --output /tmp/golden_eval_report.json"
    gate_cmd = "python -m evals.eval_gate_cli /tmp/golden_eval_report.json"

    assert content.index(generate_cmd) < content.index(gate_cmd)


# 4. Verifies that no static JSON generation is used (e.g. mocking a successful run using static files)
def test_backend_ci_golden_gate_uses_generated_report_not_static_json():
    workflow = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "backend-ci.yml"
    content = workflow.read_text(encoding="utf-8")

    assert "cat > /tmp/golden_eval_report.json" not in content
    assert '"pass_rate": 1.0' not in content


# 5. Verifies that no threshold overrides (CLI flags or env variables) are used, keeping default policy intact
def test_backend_ci_golden_gate_does_not_use_threshold_overrides():
    workflow = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "backend-ci.yml"
    content = workflow.read_text(encoding="utf-8")

    assert "--min-pass-rate" not in content
    assert "--max-failed" not in content
    assert "GOLDEN_MIN_PASS_RATE" not in content


# 6. Verifies that the golden gate execution does not use environment variables or secrets for network/db access
def test_backend_ci_golden_gate_does_not_use_secrets_or_network_env():
    workflow = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "backend-ci.yml"
    content = workflow.read_text(encoding="utf-8")

    lines = content.splitlines()
    golden_steps_started = False
    golden_steps_lines = []
    for line in lines:
        if "Run golden eval profile" in line:
            golden_steps_started = True
        if golden_steps_started:
            # Stop at the start of the next top-level job (a 2-space-indented
            # `<job>:` key) so the scan stays within the backend-tests job.
            # Without this bound the scan runs to EOF and bleeds into sibling
            # jobs (e.g. oracle-integration) whose own env: blocks are unrelated
            # to the golden gate's hermeticity.
            if golden_steps_lines and re.match(r"^  [A-Za-z0-9_-]+:\s*$", line):
                break
            golden_steps_lines.append(line)

    golden_block = "\n".join(golden_steps_lines)

    assert "env:" not in golden_block
    assert "secrets" not in golden_block
    assert "secrets." not in golden_block


# 7. Verifies that the golden eval report still passes the gate locally under default release gate settings
def test_golden_eval_report_contract_still_passes_gate_locally(tmp_path):
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
