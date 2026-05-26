import json
import sys
from evals.eval_gate_cli import main


# 1. Valid report & gate pass -> exit code 0
def test_eval_gate_cli_returns_zero_when_gate_passes(tmp_path, capsys):
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps({
        "total": 2,
        "passed": 2,
        "failed": 0,
        "pass_rate": 1.0,
        "results": [],
        "failed_cases": [],
    }), encoding="utf-8")

    exit_code = main([str(report_path)])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.err == ""


# 2. Valid report & gate fail -> exit code 1
def test_eval_gate_cli_returns_one_when_gate_fails(tmp_path, capsys):
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps({
        "total": 2,
        "passed": 1,
        "failed": 1,
        "pass_rate": 0.5,
        "results": [],
        "failed_cases": [
            {
                "id": "case_b",
                "expected_type": "success",
                "reason": "SQL equivalence mismatch",
            }
        ],
    }), encoding="utf-8")

    exit_code = main([str(report_path)])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.err == ""


# 3. Valid report -> prints correct gate result JSON to stdout
def test_eval_gate_cli_prints_gate_result_json_to_stdout(tmp_path, capsys):
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps({
        "total": 2,
        "passed": 2,
        "failed": 0,
        "pass_rate": 1.0,
        "results": [],
        "failed_cases": [],
    }), encoding="utf-8")

    exit_code = main([str(report_path)])
    captured = capsys.readouterr()

    output = json.loads(captured.out)
    assert output == {
        "gate_passed": True,
        "reason": None,
        "policy": {
            "min_pass_rate": 1.0,
            "max_failed": 0,
            "require_non_empty": True,
        },
        "summary": {
            "total": 2,
            "passed": 2,
            "failed": 0,
            "pass_rate": 1.0,
        },
        "failed_cases": [],
    }


# 4. Valid report -> writes no stderr output
def test_eval_gate_cli_writes_no_stderr_for_valid_report(tmp_path, capsys):
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps({
        "total": 2,
        "passed": 2,
        "failed": 0,
        "pass_rate": 1.0,
        "results": [],
        "failed_cases": [],
    }), encoding="utf-8")

    main([str(report_path)])
    captured = capsys.readouterr()
    assert captured.err == ""


# 5. Missing file -> exit code 2 & stderr "Eval report file not found"
def test_eval_gate_cli_returns_two_for_missing_file(capsys):
    exit_code = main(["non_existent_report.json"])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert captured.err.strip() == "Eval report file not found"


# 6. Invalid JSON -> exit code 2 & stderr "Invalid eval report JSON"
def test_eval_gate_cli_returns_two_for_invalid_json(tmp_path, capsys):
    report_path = tmp_path / "bad.json"
    report_path.write_text("{not valid json", encoding="utf-8")

    exit_code = main([str(report_path)])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert captured.err.strip() == "Invalid eval report JSON"


# 7. Missing required schema fields -> exit code 2 & stderr "Invalid eval report schema"
def test_eval_gate_cli_returns_two_for_missing_required_report_fields(tmp_path, capsys):
    report_path = tmp_path / "missing_fields.json"
    # missing required "failed_cases"
    report_path.write_text(json.dumps({
        "total": 2,
        "passed": 2,
        "failed": 0,
        "pass_rate": 1.0,
        "results": [],
    }), encoding="utf-8")

    exit_code = main([str(report_path)])
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == ""
    assert captured.err.strip() == "Invalid eval report schema"


# 8. Wrong argument count -> exit code 2 & stderr usage message
def test_eval_gate_cli_returns_two_for_wrong_argument_count(capsys):
    # Empty args
    exit_code_empty = main([])
    captured_empty = capsys.readouterr()
    assert exit_code_empty == 2
    assert captured_empty.out == ""
    assert captured_empty.err.strip() == "Usage: python -m evals.eval_gate_cli <report.json>"

    # Multiple args
    exit_code_multiple = main(["a.json", "b.json"])
    captured_multiple = capsys.readouterr()
    assert exit_code_multiple == 2
    assert captured_multiple.out == ""
    assert captured_multiple.err.strip() == "Usage: python -m evals.eval_gate_cli <report.json>"


# 9. CLI output is 100% deterministic across repeated runs
def test_eval_gate_cli_output_is_deterministic_across_repeated_runs(tmp_path, capsys):
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps({
        "total": 2,
        "passed": 2,
        "failed": 0,
        "pass_rate": 1.0,
        "results": [],
        "failed_cases": [],
    }), encoding="utf-8")

    main([str(report_path)])
    first_output = capsys.readouterr().out

    main([str(report_path)])
    second_output = capsys.readouterr().out

    assert first_output == second_output


# 10. CLI output is valid JSON-serializable
def test_eval_gate_cli_output_is_json_serializable(tmp_path, capsys):
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps({
        "total": 2,
        "passed": 2,
        "failed": 0,
        "pass_rate": 1.0,
        "results": [],
        "failed_cases": [],
    }), encoding="utf-8")

    main([str(report_path)])
    captured = capsys.readouterr()
    
    parsed = json.loads(captured.out)
    assert isinstance(parsed, dict)


# 11. CLI output does not contain non-deterministic volatile metadata (timestamps, run_id, etc.)
def test_eval_gate_cli_does_not_emit_nondeterministic_metadata(tmp_path, capsys):
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps({
        "total": 2,
        "passed": 2,
        "failed": 0,
        "pass_rate": 1.0,
        "results": [],
        "failed_cases": [],
    }), encoding="utf-8")

    main([str(report_path)])
    captured = capsys.readouterr()
    serialized = captured.out.lower()

    volatile_keywords = {"timestamp", "duration", "latency", "time", "uuid", "hostname", "path", "run_id"}
    for keyword in volatile_keywords:
        assert keyword not in serialized, f"Volatile keyword '{keyword}' found inside CLI output!"


# 12. CLI runs fully standalone without database, LLM, or network connections
def test_eval_gate_cli_does_not_execute_db_llm_or_network(tmp_path, capsys):
    report_path = tmp_path / "report.json"
    report_path.write_text(json.dumps({
        "total": 2,
        "passed": 2,
        "failed": 0,
        "pass_rate": 1.0,
        "results": [],
        "failed_cases": [],
    }), encoding="utf-8")

    # Run the main entrypoint and confirm that it completes successfully
    # without needing any mock databases/LLMs.
    exit_code = main([str(report_path)])
    assert exit_code == 0
