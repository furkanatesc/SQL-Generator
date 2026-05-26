from app.eval.checks import check_expected_sql_equivalence
from app.eval.models import GoldenCase
from app.eval.dataset_resolver import get_cases_for_profile
from app.eval.profiles import EvalProfile
from app.eval.runner import EvaluationRunner
from app.eval.fake_pipeline import DeterministicFakePipeline
from app.trace.models import NL2SQLTrace


# 1. Passes for semantically equivalent SQL
def test_expected_sql_equivalence_check_passes_for_semantically_equivalent_sql():
    case = GoldenCase(
        case_id="golden_select_user_names",
        natural_query="List all user names",
        expected_sql="SELECT name FROM users",
    )
    trace = NL2SQLTrace(
        raw_query="List all user names",
        sql_valid=True,
        selected_tables=["USERS"],
        generated_sql="select name from users;",
    )

    result = check_expected_sql_equivalence(trace, case)

    assert result.name == "expected_sql_equivalence"
    assert result.passed is True
    assert result.message == ""


# 2. Ignores formatting, whitespace, keywords case, and trailing semicolon
def test_expected_sql_equivalence_check_ignores_formatting_keyword_case_and_semicolon():
    case = GoldenCase(
        case_id="golden_select_user_names",
        natural_query="List all user names",
        expected_sql="SELECT name FROM users",
    )
    trace = NL2SQLTrace(
        raw_query="List all user names",
        sql_valid=True,
        selected_tables=["USERS"],
        generated_sql="  SELECT\n    name\n  FROM\n    users;  ",
    )

    result = check_expected_sql_equivalence(trace, case)

    assert result.passed is True


# 3. Fails for different selected columns
def test_expected_sql_equivalence_check_fails_for_different_selected_columns():
    case = GoldenCase(
        case_id="golden_select_user_names",
        natural_query="List all user names",
        expected_sql="SELECT name FROM users",
    )
    trace = NL2SQLTrace(
        raw_query="List all user names",
        sql_valid=True,
        selected_tables=["USERS"],
        generated_sql="SELECT id FROM users",
    )

    result = check_expected_sql_equivalence(trace, case)

    assert result.passed is False
    assert result.message == "Generated SQL is not equivalent to expected_sql"


# 4. Fails for different source table
def test_expected_sql_equivalence_check_fails_for_different_source_table():
    case = GoldenCase(
        case_id="golden_select_user_names",
        natural_query="List all user names",
        expected_sql="SELECT name FROM users",
    )
    trace = NL2SQLTrace(
        raw_query="List all user names",
        sql_valid=True,
        selected_tables=["CUSTOMERS"],
        generated_sql="SELECT name FROM customers",
    )

    result = check_expected_sql_equivalence(trace, case)

    assert result.passed is False
    assert result.message == "Generated SQL is not equivalent to expected_sql"


# 5. Runner automatically injects expected_sql_equivalence check if expected_sql exists
def test_runner_adds_expected_sql_equivalence_check_when_expected_sql_exists():
    cases = get_cases_for_profile(EvalProfile.GOLDEN)
    runner = EvaluationRunner(pipeline_factory=lambda store: DeterministicFakePipeline(store))

    result = runner.run_case(cases[0])

    check_names = [check.name for check in result.checks]
    assert "expected_sql_equivalence" in check_names


# 6. Runner does not require expected_sql for legacy/smoke cases without it
def test_runner_does_not_require_expected_sql_for_legacy_smoke_case():
    cases = get_cases_for_profile(EvalProfile.SMOKE)
    runner = EvaluationRunner(pipeline_factory=lambda store: DeterministicFakePipeline(store))

    result = runner.run_case(cases[0])

    check_names = [check.name for check in result.checks]
    assert "expected_sql_equivalence" not in check_names


# 7. Golden profile successfully passes all expected_sql_equivalence checks with fake pipeline
def test_golden_profile_all_cases_pass_expected_sql_equivalence_with_fake_pipeline():
    cases = get_cases_for_profile(EvalProfile.GOLDEN)
    runner = EvaluationRunner(pipeline_factory=lambda store: DeterministicFakePipeline(store))

    suite = runner.run_suite(cases, profile=EvalProfile.GOLDEN)

    assert suite.total_cases == len(cases)
    assert suite.failed == 0
    assert suite.pass_rate == 1.0

    for result in suite.results:
        checks = {check.name: check for check in result.checks}
        assert checks["expected_sql_equivalence"].passed is True


# 8. Failure message is completely stable
def test_expected_sql_equivalence_failure_message_is_stable():
    case = GoldenCase(
        case_id="golden_select_user_names",
        natural_query="List all user names",
        expected_sql="SELECT name FROM users",
    )
    trace = NL2SQLTrace(
        raw_query="List all user names",
        sql_valid=True,
        selected_tables=["USERS"],
        generated_sql="SELECT id FROM users",
    )

    result1 = check_expected_sql_equivalence(trace, case)
    result2 = check_expected_sql_equivalence(trace, case)

    assert result1.message == "Generated SQL is not equivalent to expected_sql"
    assert result1.message == result2.message


# 9. check is 100% deterministic across repeated calls
def test_expected_sql_equivalence_check_is_deterministic():
    case = GoldenCase(
        case_id="golden_select_user_names",
        natural_query="List all user names",
        expected_sql="SELECT name FROM users",
    )
    trace = NL2SQLTrace(
        raw_query="List all user names",
        sql_valid=True,
        selected_tables=["USERS"],
        generated_sql="SELECT id FROM users",
    )

    results = [check_expected_sql_equivalence(trace, case) for _ in range(10)]
    for r in results[1:]:
        assert r.passed == results[0].passed
        assert r.message == results[0].message
        assert r.details == results[0].details


# 10. Does not execute database, LLM, or network
def test_expected_sql_equivalence_does_not_use_db_llm_or_network():
    case = GoldenCase(
        case_id="golden_select_user_names",
        natural_query="List all user names",
        expected_sql="SELECT name FROM users",
    )
    trace = NL2SQLTrace(
        raw_query="List all user names",
        sql_valid=True,
        selected_tables=["USERS"],
        generated_sql="SELECT name FROM users",
    )

    result = check_expected_sql_equivalence(trace, case)
    assert result.passed is True
