import pytest
from app.eval.sql_columns import extract_sql_columns
from app.eval.checks import check_expected_columns
from app.eval.models import GoldenCase
from app.trace.models import NL2SQLTrace
from app.eval.runner import EvaluationRunner

def test_extract_sql_columns_simple():
    sql = "SELECT id, name FROM customers"
    extracted = extract_sql_columns(sql)
    assert extracted == {"ID", "NAME"}

def test_extract_sql_columns_qualified():
    sql = "SELECT c.id, c.name FROM customers c"
    extracted = extract_sql_columns(sql)
    # Checks that both simple and qualified variants are extracted for robustness
    assert "ID" in extracted
    assert "C.ID" in extracted
    assert "NAME" in extracted
    assert "C.NAME" in extracted

def test_check_expected_columns_passes_all_exist():
    trace = NL2SQLTrace(generated_sql="SELECT id, name FROM customers")
    case = GoldenCase(
        case_id="test_cols",
        natural_query="get id and name",
        expected_columns=["id", "name"]
    )
    result = check_expected_columns(trace, case)
    assert result.passed is True
    assert result.name == "expected_columns"
    assert result.details["missing"] == []

def test_check_expected_columns_fails_when_missing():
    trace = NL2SQLTrace(generated_sql="SELECT id FROM customers")
    case = GoldenCase(
        case_id="test_cols",
        natural_query="get id and name",
        expected_columns=["id", "name"]
    )
    result = check_expected_columns(trace, case)
    assert result.passed is False
    assert result.details["missing"] == ["NAME"]
    assert "Missing expected columns" in result.message

def test_case_insensitive_matching():
    trace = NL2SQLTrace(generated_sql="SELECT ID, Name FROM customers")
    case = GoldenCase(
        case_id="test_cols",
        natural_query="get id and name",
        expected_columns=["id", "NAME"]
    )
    result = check_expected_columns(trace, case)
    assert result.passed is True

def test_parse_failure_controlled_fail_no_exception():
    trace = NL2SQLTrace(generated_sql="SELECT FROM WHERE;")  # malformed syntax
    case = GoldenCase(
        case_id="test_cols",
        natural_query="get id",
        expected_columns=["id"]
    )
    # Should not raise exception, but return passed=False
    result = check_expected_columns(trace, case)
    assert result.passed is False
    assert result.details["missing"] == ["ID"]
    assert "Failed to parse SQL or no columns extracted" in result.message

def test_runner_includes_expected_columns_check():
    # Construct a pipeline factory that returns a mock pipeline saving a specific trace
    trace = NL2SQLTrace(
        generated_sql="SELECT id FROM customers",
        sql_valid=True,
        selected_tables=["customers"]
    )

    class FakePipeline:
        def __init__(self, store):
            self.store = store
        def run_pipeline(self, job_id, natural_query):
            self.store.saved = [trace]

    runner = EvaluationRunner(pipeline_factory=lambda store: FakePipeline(store))
    case = GoldenCase(
        case_id="test_cols_runner",
        natural_query="get id and name",
        expected_columns=["id", "name"]
    )
    result = runner.run_case(case)
    # The runner must evaluate check_expected_columns
    assert result.passed is False
    assert any(c.name == "expected_columns" for c in result.checks)
    col_check = next(c for c in result.checks if c.name == "expected_columns")
    assert col_check.passed is False
    assert col_check.details["missing"] == ["NAME"]
