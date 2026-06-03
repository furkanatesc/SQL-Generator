import pytest
from app.eval.models import EvalCheckResult, EvalCaseResult, EvalSuiteResult
from app.eval.run_eval import suite_result_to_report_dict

def test_suite_result_to_report_dict_includes_checks_and_failed_checks():
    # Construct check results
    check1 = EvalCheckResult(name="sql_valid", passed=True, message="", details={"sql_valid": True})
    check2 = EvalCheckResult(name="expected_columns", passed=False, message="Missing expected columns: ['NAME']", details={
        "expected": ["ID", "NAME"],
        "extracted": ["ID"],
        "missing": ["NAME"]
    })
    
    case_result = EvalCaseResult(
        case_id="case_1",
        passed=False,
        checks=[check1, check2],
        generated_sql="SELECT id FROM customers",
        error_type=None,
        error_message=None
    )
    
    suite_result = EvalSuiteResult(
        profile="smoke",
        total_cases=1,
        passed=0,
        failed=1,
        pass_rate=0.0,
        results=[case_result]
    )
    
    report = suite_result_to_report_dict(suite_result)
    
    assert report["total"] == 1
    assert report["passed"] == 0
    assert report["failed"] == 1
    
    # Assert result entry
    res = report["results"][0]
    assert res["id"] == "case_1"
    assert res["passed"] is False
    assert res["reason"] == "Missing expected columns: ['NAME']"
    assert res["actual"]["generated_sql"] == "SELECT id FROM customers"
    
    # Assert checks list
    assert len(res["checks"]) == 2
    assert res["checks"][0]["name"] == "sql_valid"
    assert res["checks"][0]["passed"] is True
    assert res["checks"][1]["name"] == "expected_columns"
    assert res["checks"][1]["passed"] is False
    assert res["checks"][1]["details"]["missing"] == ["NAME"]
    
    # Assert failed_checks list
    assert len(res["failed_checks"]) == 1
    assert res["failed_checks"][0]["name"] == "expected_columns"
    assert res["failed_checks"][0]["message"] == "Missing expected columns: ['NAME']"
    
    # Assert failed_cases entry contains failed checks with missing column details
    fc = report["failed_cases"][0]
    assert fc["id"] == "case_1"
    assert len(fc["failed_checks"]) == 1
    assert fc["failed_checks"][0]["name"] == "expected_columns"
    assert fc["failed_checks"][0]["details"]["missing"] == ["NAME"]

def test_reason_selection_deterministic():
    # Case 1: First failed check message is populated
    c1 = EvalCheckResult(name="check1", passed=False, message="Custom check message")
    res1 = EvalCaseResult(case_id="case1", passed=False, checks=[c1])
    report1 = suite_result_to_report_dict(EvalSuiteResult("smoke", 1, 0, 1, 0.0, [res1]))
    assert report1["results"][0]["reason"] == "Custom check message"

    # Case 2: Message is empty/whitespace -> falls back to "Check failed: <name>"
    c2 = EvalCheckResult(name="check2", passed=False, message="  ")
    res2 = EvalCaseResult(case_id="case2", passed=False, checks=[c2])
    report2 = suite_result_to_report_dict(EvalSuiteResult("smoke", 1, 0, 1, 0.0, [res2]))
    assert report2["results"][0]["reason"] == "Check failed: check2"

    # Case 3: No checks failed/present -> falls back to error_message
    res3 = EvalCaseResult(case_id="case3", passed=False, checks=[], error_message="Pipeline execution crashed")
    report3 = suite_result_to_report_dict(EvalSuiteResult("smoke", 1, 0, 1, 0.0, [res3]))
    assert report3["results"][0]["reason"] == "Pipeline execution crashed"

    # Case 4: No error message either -> falls back to "Unknown failure"
    res4 = EvalCaseResult(case_id="case4", passed=False, checks=[])
    report4 = suite_result_to_report_dict(EvalSuiteResult("smoke", 1, 0, 1, 0.0, [res4]))
    assert report4["results"][0]["reason"] == "Unknown failure"
