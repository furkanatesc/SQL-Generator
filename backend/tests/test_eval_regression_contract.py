import pytest
from app.eval.models import EvalCheckResult, GoldenCase
from app.eval.profiles import EvalProfile
from app.eval.dataset_resolver import get_cases_for_profile
from app.eval.runner import EvaluationRunner
from app.eval.reporting import check_result_to_dict, suite_result_to_dict
from app.trace.models import NL2SQLTrace

class DeterministicPipeline:
    def __init__(self, store, sql="SELECT * FROM customers", tables=None, sql_valid=True):
        self.store = store
        self.sql = sql
        self.tables = tables or ["CUSTOMERS"]
        self.sql_valid = sql_valid

    def run_pipeline(self, *, natural_query: str, **kwargs):
        self.store.save(
            NL2SQLTrace(
                raw_query=natural_query,
                sql_valid=self.sql_valid,
                selected_tables=self.tables,
                generated_sql=self.sql,
            )
        )

def make_runner(sql="SELECT * FROM customers", tables=None, sql_valid=True):
    return EvaluationRunner(
        pipeline_factory=lambda store: DeterministicPipeline(
            store=store,
            sql=sql,
            tables=tables,
            sql_valid=sql_valid,
        )
    )

def test_smoke_profile_json_report_contract_is_stable():
    cases = get_cases_for_profile(EvalProfile.SMOKE)
    runner = make_runner()
    suite_result = runner.run_suite(cases, profile=EvalProfile.SMOKE)
    report = suite_result_to_dict(suite_result)

    assert report["profile"] == "smoke"
    assert set(report.keys()) == {"profile", "summary", "results"}

    summary = report["summary"]
    assert set(summary.keys()) == {"total_cases", "passed", "failed", "pass_rate"}
    assert summary["total_cases"] == 1

    assert len(report["results"]) == 1
    case = report["results"][0]
    assert set(case.keys()) == {
        "case_id",
        "passed",
        "generated_sql",
        "error_type",
        "checks",
    }
    assert case["case_id"] == "smoke_list_customers"

def test_golden_profile_report_has_structural_invariants():
    cases = get_cases_for_profile(EvalProfile.GOLDEN)
    runner = make_runner()
    suite_result = runner.run_suite(cases, profile=EvalProfile.GOLDEN)
    report = suite_result_to_dict(suite_result)

    assert report["profile"] == "golden"
    summary = report["summary"]
    assert summary["total_cases"] > 1
    assert summary["passed"] + summary["failed"] == summary["total_cases"]
    assert 0.0 <= summary["pass_rate"] <= 1.0
    assert len(report["results"]) == summary["total_cases"]

    case_ids = [r["case_id"] for r in report["results"]]
    assert len(case_ids) == len(set(case_ids))

    for result in report["results"]:
        assert isinstance(result["checks"], list)
        assert "case_id" in result
        assert "passed" in result
        assert "generated_sql" in result
        assert "error_type" in result

def test_check_result_json_shape_is_stable():
    check = EvalCheckResult(
        name="sql_valid",
        passed=True,
        message="",
        details={"sql_valid": True},
    )

    result = check_result_to_dict(check)
    assert set(result.keys()) == {"name", "passed", "message", "details"}

def test_eval_check_names_are_stable():
    case = GoldenCase(
        case_id="check_names",
        natural_query="List customers",
        expected_tables=["CUSTOMERS"],
        required_sql_fragments=["SELECT"],
        forbidden_sql_fragments=["DROP"],
        required_sql_features=["join"],
        forbidden_sql_features=["aggregation"],
    )

    runner = make_runner()
    result = runner.run_case(case)
    check_names = {check.name for check in result.checks}

    assert "sql_valid" in check_names
    assert "expected_tables" in check_names
    assert "required_sql_fragments" in check_names
    assert "forbidden_sql_fragments" in check_names
    assert "required_sql_features" in check_names
    assert "forbidden_sql_features" in check_names

def test_suite_summary_arithmetic_invariants_are_stable():
    cases = get_cases_for_profile(EvalProfile.GOLDEN)
    runner = make_runner()
    suite_result = runner.run_suite(cases, profile=EvalProfile.GOLDEN)
    
    assert suite_result.total_cases == len(suite_result.results)
    assert suite_result.total_cases == suite_result.passed + suite_result.failed
    if suite_result.total_cases:
        assert suite_result.pass_rate == suite_result.passed / suite_result.total_cases
    else:
        assert suite_result.pass_rate == 0.0

def test_empty_suite_summary_arithmetic_invariants():
    runner = make_runner()
    suite_result = runner.run_suite([], profile=EvalProfile.SMOKE)
    
    assert suite_result.total_cases == 0
    assert suite_result.passed == 0
    assert suite_result.failed == 0
    assert suite_result.pass_rate == 0.0
    assert len(suite_result.results) == 0
