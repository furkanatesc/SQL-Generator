import json
import pytest
from app.eval.run_eval import main
from app.eval.models import EvalSuiteResult

def test_eval_cli_returns_zero_for_successful_smoke_profile(capsys):
    exit_code = main(["--profile", "smoke"])
    assert exit_code == 0

def test_eval_cli_returns_zero_for_successful_golden_profile(capsys):
    exit_code = main(["--profile", "golden"])
    assert exit_code == 0

def test_eval_cli_json_output_contract_for_smoke(capsys):
    exit_code = main(["--profile", "smoke", "--json"])

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["profile"] == "smoke"
    assert "summary" in payload
    assert "results" in payload
    assert captured.err == ""

def test_eval_cli_json_output_does_not_include_exit_code(capsys):
    exit_code = main(["--profile", "smoke", "--json"])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert "exit_code" not in payload

def test_eval_cli_invalid_profile_returns_two_and_writes_stderr(capsys):
    exit_code = main(["--profile", "prod"])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "Invalid eval profile 'prod'" in captured.err

def test_eval_cli_large_schema_reserved_returns_two(capsys):
    exit_code = main(["--profile", "large_schema"])

    captured = capsys.readouterr()

    assert exit_code == 2
    assert "large_schema profile is reserved" in captured.err

def test_eval_cli_returns_one_when_suite_has_failed_cases(monkeypatch):
    class FakeRunner:
        def run_suite(self, cases, profile):
            return EvalSuiteResult(
                profile="smoke",
                total_cases=1,
                passed=0,
                failed=1,
                pass_rate=0.0,
                results=[],
            )

    monkeypatch.setattr("app.eval.run_eval.build_runner", lambda: FakeRunner())

    exit_code = main(["--profile", "smoke"])

    assert exit_code == 1

def test_eval_cli_text_output_includes_failure_diagnostics(monkeypatch, capsys):
    from app.eval.models import EvalCaseResult
    class FakeRunner:
        def run_suite(self, cases, profile):
            return EvalSuiteResult(
                profile="smoke",
                total_cases=1,
                passed=0,
                failed=1,
                pass_rate=0.0,
                results=[
                    EvalCaseResult(
                        case_id="bad_case",
                        passed=False,
                        checks=[],
                        generated_sql=None,
                        error_type="PipelineExecutionError",
                        error_message="boom",
                    )
                ],
            )

    monkeypatch.setattr("app.eval.run_eval.build_runner", lambda: FakeRunner())

    exit_code = main(["--profile", "smoke"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "[FAIL] bad_case" in captured.out
    assert "Error type: PipelineExecutionError" in captured.out
    assert "Error message: boom" in captured.out

def test_eval_cli_text_output_keeps_summary_block(capsys):
    exit_code = main(["--profile", "smoke"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "Evaluation Summary" in captured.out
    assert "Profile: smoke" in captured.out
    assert "Total cases:" in captured.out
    assert "Pass rate:" in captured.out
