import json
from copy import deepcopy
from evals.eval_gate import evaluate_release_gate


# 1. Passes when all cases pass under default policy
def test_release_gate_passes_when_all_cases_pass_default_policy():
    report = {
        "total": 2,
        "passed": 2,
        "failed": 0,
        "pass_rate": 1.0,
        "results": [],
        "failed_cases": [],
    }

    result = evaluate_release_gate(report)

    assert result == {
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


# 2. Fails when any case fails under default policy
def test_release_gate_fails_when_any_case_fails_default_policy():
    report = {
        "total": 2,
        "passed": 1,
        "failed": 1,
        "pass_rate": 0.5,
        "results": [],
        "failed_cases": [
            {
                "id": "case_b",
                "expected_type": "success",
                "reason": "Missing SQL fragment: orders",
            }
        ],
    }

    result = evaluate_release_gate(report)

    assert result["gate_passed"] is False
    assert result["reason"] == "Pass rate below threshold"
    assert result["failed_cases"] == [
        {
            "id": "case_b",
            "expected_type": "success",
            "reason": "Missing SQL fragment: orders",
        }
    ]


# 3. Fails when pass rate is below custom threshold
def test_release_gate_fails_when_pass_rate_below_threshold():
    report = {
        "total": 4,
        "passed": 3,
        "failed": 1,
        "pass_rate": 0.75,
        "results": [],
        "failed_cases": [
            {
                "id": "case_x",
                "expected_type": "success",
                "reason": "mismatch",
            }
        ],
    }
    
    result = evaluate_release_gate(report, policy={"min_pass_rate": 0.8})
    assert result["gate_passed"] is False
    assert result["reason"] == "Pass rate below threshold"


# 4. Fails when failed count is above threshold (even if pass rate threshold met)
def test_release_gate_fails_when_failed_count_above_threshold():
    report = {
        "total": 4,
        "passed": 3,
        "failed": 1,
        "pass_rate": 0.75,
        "results": [],
        "failed_cases": [
            {
                "id": "case_x",
                "expected_type": "success",
                "reason": "mismatch",
            }
        ],
    }
    
    result = evaluate_release_gate(report, policy={"min_pass_rate": 0.5, "max_failed": 0})
    assert result["gate_passed"] is False
    assert result["reason"] == "Failed case count above threshold"


# 5. Fails empty eval report by default (require_non_empty = True)
def test_release_gate_fails_empty_eval_report_by_default():
    report = {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "pass_rate": 0.0,
        "results": [],
        "failed_cases": [],
    }

    result = evaluate_release_gate(report)

    assert result["gate_passed"] is False
    assert result["reason"] == "No eval cases were run"


# 6. Allows custom threshold policy and respects it fully
def test_release_gate_allows_custom_threshold_policy():
    report = {
        "total": 4,
        "passed": 3,
        "failed": 1,
        "pass_rate": 0.75,
        "results": [],
        "failed_cases": [
            {
                "id": "case_x",
                "expected_type": "success",
                "reason": "mismatch",
            }
        ],
    }
    custom_policy = {
        "min_pass_rate": 0.7,
        "max_failed": 2,
        "require_non_empty": True,
    }
    
    result = evaluate_release_gate(report, policy=custom_policy)
    assert result == {
        "gate_passed": True,
        "reason": None,
        "policy": {
            "min_pass_rate": 0.7,
            "max_failed": 2,
            "require_non_empty": True,
        },
        "summary": {
            "total": 4,
            "passed": 3,
            "failed": 1,
            "pass_rate": 0.75,
        },
        "failed_cases": [
            {
                "id": "case_x",
                "expected_type": "success",
                "reason": "mismatch",
            }
        ],
    }


# 7. Stable machine-readable schema test (exact types and keys)
def test_release_gate_output_has_stable_machine_readable_schema():
    report = {
        "total": 1,
        "passed": 1,
        "failed": 0,
        "pass_rate": 1.0,
        "results": [],
        "failed_cases": [],
    }
    result = evaluate_release_gate(report)
    
    assert set(result.keys()) == {"gate_passed", "reason", "policy", "summary", "failed_cases"}
    assert isinstance(result["gate_passed"], bool)
    assert result["reason"] is None or isinstance(result["reason"], str)
    
    assert set(result["policy"].keys()) == {"min_pass_rate", "max_failed", "require_non_empty"}
    assert isinstance(result["policy"]["min_pass_rate"], float)
    assert isinstance(result["policy"]["max_failed"], int)
    assert isinstance(result["policy"]["require_non_empty"], bool)
    
    assert set(result["summary"].keys()) == {"total", "passed", "failed", "pass_rate"}
    assert isinstance(result["summary"]["total"], int)
    assert isinstance(result["summary"]["passed"], int)
    assert isinstance(result["summary"]["failed"], int)
    assert isinstance(result["summary"]["pass_rate"], float)
    
    assert isinstance(result["failed_cases"], list)


# 8. Correctly propagates failed_cases from report
def test_release_gate_includes_failed_cases_from_report():
    report = {
        "total": 2,
        "passed": 1,
        "failed": 1,
        "pass_rate": 0.5,
        "results": [],
        "failed_cases": [
            {
                "id": "case_a",
                "expected_type": "success",
                "reason": "mismatch",
            }
        ],
    }
    result = evaluate_release_gate(report)
    assert result["failed_cases"] == [
        {
            "id": "case_a",
            "expected_type": "success",
            "reason": "mismatch",
        }
    ]


# 9. Gate output is 100% JSON-serializable
def test_release_gate_is_json_serializable():
    report = {
        "total": 2,
        "passed": 1,
        "failed": 1,
        "pass_rate": 0.5,
        "results": [],
        "failed_cases": [
            {
                "id": "case_a",
                "expected_type": "success",
                "reason": "mismatch",
            }
        ],
    }
    result = evaluate_release_gate(report)
    serialized = json.dumps(result)
    parsed = json.loads(serialized)
    assert parsed == result


# 10. Gate decision is deterministic across repeated calls
def test_release_gate_is_deterministic_across_repeated_calls():
    report = {
        "total": 2,
        "passed": 1,
        "failed": 1,
        "pass_rate": 0.5,
        "results": [],
        "failed_cases": [
            {
                "id": "case_a",
                "expected_type": "success",
                "reason": "mismatch",
            }
        ],
    }
    results = [evaluate_release_gate(report) for _ in range(10)]
    for r in results[1:]:
        assert r == results[0]


# 11. Does not mutate the input report
def test_release_gate_does_not_mutate_input_report():
    report = {
        "total": 2,
        "passed": 1,
        "failed": 1,
        "pass_rate": 0.5,
        "results": [],
        "failed_cases": [
            {
                "id": "case_a",
                "expected_type": "success",
                "reason": "mismatch",
            }
        ],
    }
    report_copy = deepcopy(report)
    evaluate_release_gate(report)
    assert report == report_copy


# 12. Does not include volatile nondeterministic metadata (timestamps, durations, paths, UUIDs, etc.)
def test_release_gate_does_not_include_nondeterministic_metadata():
    report = {
        "total": 2,
        "passed": 1,
        "failed": 1,
        "pass_rate": 0.5,
        "results": [],
        "failed_cases": [
            {
                "id": "case_a",
                "expected_type": "success",
                "reason": "mismatch",
            }
        ],
    }
    result = evaluate_release_gate(report)
    serialized = json.dumps(result).lower()
    
    volatile_keywords = {"timestamp", "duration", "latency", "time", "uuid", "hostname", "path", "run_id"}
    for keyword in volatile_keywords:
        assert keyword not in serialized, f"Volatile keyword '{keyword}' found inside release gate output!"
