from app.eval.models import GoldenCase
from app.eval.checks import (
    check_sql_valid,
    check_expected_tables,
    check_required_sql_fragments,
    check_forbidden_sql_fragments,
    check_required_sql_features,
    check_forbidden_sql_features,
)
from app.eval.golden_cases import GOLDEN_CASES
from app.trace.models import NL2SQLTrace

def test_check_sql_valid_passes_when_trace_sql_valid_true():
    trace = NL2SQLTrace(sql_valid=True)
    result = check_sql_valid(trace)
    assert result.passed is True
    assert result.name == "sql_valid"

def test_check_sql_valid_fails_when_trace_sql_valid_false():
    trace = NL2SQLTrace(sql_valid=False, error_type="SyntaxError")
    result = check_sql_valid(trace)
    assert result.passed is False
    assert "not valid" in result.message
    assert result.details["error_type"] == "SyntaxError"

def test_expected_tables_check_passes_when_all_expected_selected():
    trace = NL2SQLTrace(selected_tables=["users", "orders"])
    case = GoldenCase(case_id="test", natural_query="test", expected_tables=["USERS", "ORDERS"])
    result = check_expected_tables(trace, case)
    assert result.passed is True

def test_expected_tables_check_reports_missing_tables():
    trace = NL2SQLTrace(selected_tables=["users"])
    case = GoldenCase(case_id="test", natural_query="test", expected_tables=["USERS", "ORDERS"])
    result = check_expected_tables(trace, case)
    assert result.passed is False
    assert "ORDERS" in result.details["missing"]
    assert "ORDERS" in result.message

def test_required_sql_fragments_check_passes():
    trace = NL2SQLTrace(generated_sql="SELECT * FROM users JOIN orders")
    case = GoldenCase(case_id="test", natural_query="test", required_sql_fragments=["JOIN", "SELECT"])
    result = check_required_sql_fragments(trace, case)
    assert result.passed is True

def test_required_sql_fragments_check_reports_missing_fragment():
    trace = NL2SQLTrace(generated_sql="SELECT * FROM users")
    case = GoldenCase(case_id="test", natural_query="test", required_sql_fragments=["JOIN"])
    result = check_required_sql_fragments(trace, case)
    assert result.passed is False
    assert "JOIN" in result.details["missing"]
    assert "JOIN" in result.message

def test_forbidden_sql_fragments_check_passes_when_absent():
    trace = NL2SQLTrace(generated_sql="SELECT * FROM users")
    case = GoldenCase(case_id="test", natural_query="test", forbidden_sql_fragments=["DELETE", "DROP"])
    result = check_forbidden_sql_fragments(trace, case)
    assert result.passed is True

def test_forbidden_sql_fragments_check_fails_when_present():
    trace = NL2SQLTrace(generated_sql="DELETE FROM users")
    case = GoldenCase(case_id="test", natural_query="test", forbidden_sql_fragments=["DELETE"])
    result = check_forbidden_sql_fragments(trace, case)
    assert result.passed is False
    assert "DELETE" in result.details["present"]
    assert "DELETE" in result.message

def test_golden_case_ids_are_unique():
    ids = [case.case_id for case in GOLDEN_CASES]
    assert len(ids) == len(set(ids))

def test_required_sql_features_check_passes():
    trace = NL2SQLTrace(generated_sql="SELECT * FROM users JOIN orders ON users.id = orders.user_id")
    case = GoldenCase(case_id="test", natural_query="test", required_sql_features=["join"])
    result = check_required_sql_features(trace, case)
    assert result.passed is True

def test_required_sql_features_check_reports_missing_features():
    trace = NL2SQLTrace(generated_sql="SELECT * FROM users")
    case = GoldenCase(case_id="test", natural_query="test", required_sql_features=["join"])
    result = check_required_sql_features(trace, case)
    assert result.passed is False
    assert "join" in result.details["missing"]
    assert "join" in result.message

def test_forbidden_sql_features_check_passes_when_absent():
    trace = NL2SQLTrace(generated_sql="SELECT * FROM users")
    case = GoldenCase(case_id="test", natural_query="test", forbidden_sql_features=["join"])
    result = check_forbidden_sql_features(trace, case)
    assert result.passed is True

def test_forbidden_sql_features_check_fails_when_present():
    trace = NL2SQLTrace(generated_sql="SELECT * FROM users JOIN orders ON users.id = orders.user_id")
    case = GoldenCase(case_id="test", natural_query="test", forbidden_sql_features=["join"])
    result = check_forbidden_sql_features(trace, case)
    assert result.passed is False
    assert "join" in result.details["present"]
    assert "join" in result.message

def test_golden_cases_have_non_empty_natural_queries():
    for case in GOLDEN_CASES:
        assert case.natural_query.strip() != "", f"Case {case.case_id} has an empty natural query"

def test_golden_cases_use_supported_sql_features():
    SUPPORTED_SQL_FEATURES = {"join", "aggregation", "where", "group_by", "order_by", "limit"}
    for case in GOLDEN_CASES:
        for feature in case.required_sql_features:
            assert feature in SUPPORTED_SQL_FEATURES, f"Unsupported required feature {feature} in case {case.case_id}"
        for feature in case.forbidden_sql_features:
            assert feature in SUPPORTED_SQL_FEATURES, f"Unsupported forbidden feature {feature} in case {case.case_id}"
