from app.eval.models import EvalCheckResult, EvalCaseResult, EvalSuiteResult
from app.eval.reporting import check_result_to_dict, case_result_to_dict, suite_result_to_dict

def test_check_result_to_dict_includes_name_passed_message_details():
    check = EvalCheckResult(
        name="test_check",
        passed=False,
        message="Test failed",
        details={"key": "value"}
    )
    result = check_result_to_dict(check)
    assert result["name"] == "test_check"
    assert result["passed"] is False
    assert result["message"] == "Test failed"
    assert result["details"] == {"key": "value"}

def test_case_result_to_dict_includes_generated_sql_and_error_type():
    check = EvalCheckResult(name="check1", passed=True)
    case = EvalCaseResult(
        case_id="case1",
        passed=True,
        checks=[check],
        generated_sql="SELECT * FROM table",
        error_type=None
    )
    result = case_result_to_dict(case)
    assert result["case_id"] == "case1"
    assert result["passed"] is True
    assert result["generated_sql"] == "SELECT * FROM table"
    assert result["error_type"] is None
    assert len(result["checks"]) == 1
    assert result["checks"][0]["name"] == "check1"

def test_suite_result_to_dict_has_stable_summary_shape():
    suite = EvalSuiteResult(
        total_cases=10,
        passed=7,
        failed=3,
        pass_rate=0.7,
        results=[]
    )
    result = suite_result_to_dict(suite)
    assert "summary" in result
    summary = result["summary"]
    assert summary["total_cases"] == 10
    assert summary["passed"] == 7
    assert summary["failed"] == 3
    assert summary["pass_rate"] == 0.7
    assert "results" in result
    assert result["results"] == []
