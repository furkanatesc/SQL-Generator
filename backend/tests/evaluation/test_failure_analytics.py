import pytest
from dataclasses import FrozenInstanceError

from app.evaluation.execution_accuracy import SQLExecutionAccuracyCaseResult, SQLExecutionAccuracyRunResult
from app.evaluation.failure_analytics import (
    SQL_FAILURE_ANALYTICS_VERSION,
    SQLFailureCategory,
    SQLFailureSeverity,
    SQLFailureSignal,
    SQLFailureAnalysisResult,
    SQLFailureAnalyticsRunResult,
    SQLFailureAnalyzer,
    SQLFailureAnalyticsContractError,
)


def make_mock_case_result(**kwargs) -> SQLExecutionAccuracyCaseResult:
    default_args = {
        "case_id": "test_case",
        "dialect": "sqlite",
        "fixture_ref": "test_db",
        "predicted_sql": "SELECT * FROM users",
        "predicted_sql_sha256": "sha_pred",
        "gold_sql_sha256": "sha_gold",
        "passed": False,
        "comparison_policy": "exact_unordered",
        "expected_row_count": 2,
        "actual_row_count": 2,
        "normalized_expected_result": [{"id": 1}, {"id": 2}],
        "normalized_actual_result": [{"id": 1}, {"id": 2}],
        "execution_error": None,
        "duration_ms": 10.0,
        "warnings": (),
    }
    default_args.update(kwargs)
    return SQLExecutionAccuracyCaseResult(**default_args)


def test_analyzer_version_is_v1():
    assert SQL_FAILURE_ANALYTICS_VERSION == "sql_failure_analytics_v1"


def test_failure_analysis_result_is_frozen():
    res = SQLFailureAnalysisResult(
        case_id="c1",
        category=SQLFailureCategory.PASSED,
        severity=SQLFailureSeverity.INFO,
        passed=True,
        evidence="passed"
    )
    with pytest.raises((FrozenInstanceError, AttributeError)):
        res.category = SQLFailureCategory.UNKNOWN_FAILURE


def test_analyzer_marks_passed_case_as_passed():
    res = make_mock_case_result(passed=True)
    analysis = SQLFailureAnalyzer.analyze_case(res)
    assert analysis.passed is True
    assert analysis.category == SQLFailureCategory.PASSED
    assert analysis.severity == SQLFailureSeverity.INFO


def test_analyzer_classifies_empty_predicted_sql():
    res = make_mock_case_result(
        passed=False,
        execution_error="predicted_sql cannot be empty"
    )
    analysis = SQLFailureAnalyzer.analyze_case(res)
    assert analysis.passed is False
    assert analysis.category == SQLFailureCategory.EMPTY_PREDICTED_SQL
    assert analysis.severity == SQLFailureSeverity.HIGH


def test_analyzer_classifies_unsafe_sql_rejected():
    res = make_mock_case_result(
        passed=False,
        execution_error="Only read-only SELECT statements are allowed"
    )
    analysis = SQLFailureAnalyzer.analyze_case(res)
    assert analysis.passed is False
    assert analysis.category == SQLFailureCategory.UNSAFE_SQL_REJECTED
    assert analysis.severity == SQLFailureSeverity.CRITICAL


def test_analyzer_classifies_fixture_not_found():
    res = make_mock_case_result(
        passed=False,
        execution_error="Fixture database not found: test_db"
    )
    analysis = SQLFailureAnalyzer.analyze_case(res)
    assert analysis.passed is False
    assert analysis.category == SQLFailureCategory.FIXTURE_NOT_FOUND
    assert analysis.severity == SQLFailureSeverity.CRITICAL


def test_analyzer_classifies_sql_execution_error():
    res = make_mock_case_result(
        passed=False,
        execution_error="no such column: age"
    )
    analysis = SQLFailureAnalyzer.analyze_case(res)
    assert analysis.passed is False
    assert analysis.category == SQLFailureCategory.SQL_EXECUTION_ERROR
    assert analysis.severity == SQLFailureSeverity.MEDIUM


def test_analyzer_classifies_expected_result_invalid():
    res = make_mock_case_result(
        passed=False,
        execution_error="Expected result canonicalization failed: not a list"
    )
    analysis = SQLFailureAnalyzer.analyze_case(res)
    assert analysis.passed is False
    assert analysis.category == SQLFailureCategory.EXPECTED_RESULT_INVALID
    assert analysis.severity == SQLFailureSeverity.HIGH


def test_analyzer_classifies_gold_sql_execution_error():
    res = make_mock_case_result(
        passed=False,
        execution_error="Gold SQL execution failed: syntax error"
    )
    analysis = SQLFailureAnalyzer.analyze_case(res)
    assert analysis.passed is False
    assert analysis.category == SQLFailureCategory.GOLD_SQL_EXECUTION_ERROR
    assert analysis.severity == SQLFailureSeverity.HIGH


def test_analyzer_classifies_row_count_mismatch():
    res = make_mock_case_result(
        passed=False,
        expected_row_count=5,
        actual_row_count=2,
    )
    analysis = SQLFailureAnalyzer.analyze_case(res)
    assert analysis.passed is False
    assert analysis.category == SQLFailureCategory.ROW_COUNT_MISMATCH
    assert analysis.severity == SQLFailureSeverity.MEDIUM


def test_analyzer_classifies_column_shape_mismatch():
    res = make_mock_case_result(
        passed=False,
        expected_row_count=2,
        actual_row_count=2,
        normalized_expected_result=[{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}],
        normalized_actual_result=[{"id": 1, "score": 95}, {"id": 2, "score": 80}],
    )
    analysis = SQLFailureAnalyzer.analyze_case(res)
    assert analysis.passed is False
    assert analysis.category == SQLFailureCategory.COLUMN_SHAPE_MISMATCH
    assert analysis.severity == SQLFailureSeverity.MEDIUM


def test_analyzer_classifies_order_mismatch():
    # Row ordering differs, but values are identical under EXACT_UNORDERED
    res = make_mock_case_result(
        passed=False,
        comparison_policy="exact_ordered",
        expected_row_count=2,
        actual_row_count=2,
        normalized_expected_result=[{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}],
        normalized_actual_result=[{"id": 2, "name": "Bob"}, {"id": 1, "name": "Alice"}],
    )
    analysis = SQLFailureAnalyzer.analyze_case(res)
    assert analysis.passed is False
    assert analysis.category == SQLFailureCategory.ORDER_MISMATCH
    assert analysis.severity == SQLFailureSeverity.LOW


def test_analyzer_classifies_numeric_tolerance_mismatch():
    res = make_mock_case_result(
        passed=False,
        comparison_policy="numeric_tolerance",
        expected_row_count=1,
        actual_row_count=1,
        normalized_expected_result=[{"score": 95.5}],
        normalized_actual_result=[{"score": 90.0}],
    )
    analysis = SQLFailureAnalyzer.analyze_case(res)
    assert analysis.passed is False
    assert analysis.category == SQLFailureCategory.NUMERIC_TOLERANCE_MISMATCH
    assert analysis.severity == SQLFailureSeverity.LOW


def test_analyzer_classifies_value_mismatch():
    # Counts and shapes match, but values differ
    res = make_mock_case_result(
        passed=False,
        comparison_policy="exact_unordered",
        expected_row_count=2,
        actual_row_count=2,
        normalized_expected_result=[{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}],
        normalized_actual_result=[{"id": 1, "name": "Charlie"}, {"id": 2, "name": "Bob"}],
    )
    analysis = SQLFailureAnalyzer.analyze_case(res)
    assert analysis.passed is False
    assert analysis.category == SQLFailureCategory.VALUE_MISMATCH
    assert analysis.severity == SQLFailureSeverity.MEDIUM


def test_analyzer_falls_back_to_unknown_failure():
    # Missing result sets, no execution error
    res = make_mock_case_result(
        passed=False,
        normalized_actual_result=None,
        normalized_expected_result=None,
        expected_row_count=0,
        actual_row_count=0
    )
    analysis = SQLFailureAnalyzer.analyze_case(res)
    assert analysis.passed is False
    assert analysis.category == SQLFailureCategory.UNKNOWN_FAILURE


def test_analyzer_preserves_dialect_mismatch_warning_signal():
    res = make_mock_case_result(
        passed=True,
        warnings=("Harness executing SQL of dialect 'oracle' in a SQLite sandbox fixture.",)
    )
    analysis = SQLFailureAnalyzer.analyze_case(res)
    assert len(analysis.signals) == 1
    assert analysis.signals[0].name == "dialect_mismatch_warning"
    assert "oracle" in analysis.signals[0].value


def test_failure_analytics_run_result_sorts_by_case_id():
    res_c = make_mock_case_result(case_id="case_c", passed=True)
    res_a = make_mock_case_result(case_id="case_a", passed=False, execution_error="predicted_sql cannot be empty")
    res_b = make_mock_case_result(case_id="case_b", passed=False)

    run = SQLExecutionAccuracyRunResult(
        total_cases=3,
        passed_cases=1,
        failed_cases=2,
        pass_rate=1.0/3.0,
        case_results=(res_c, res_a, res_b),
        duration_ms=50.0
    )

    analysis_run = SQLFailureAnalyzer.analyze_run(run)
    assert isinstance(analysis_run, SQLFailureAnalyticsRunResult)
    assert analysis_run.case_results[0].case_id == "case_a"
    assert analysis_run.case_results[1].case_id == "case_b"
    assert analysis_run.case_results[2].case_id == "case_c"


def test_failure_analytics_run_result_counts_categories():
    res_1 = make_mock_case_result(case_id="c1", passed=True)
    res_2 = make_mock_case_result(case_id="c2", passed=False, execution_error="predicted_sql cannot be empty")
    res_3 = make_mock_case_result(case_id="c3", passed=False, expected_row_count=5, actual_row_count=2)

    run = SQLExecutionAccuracyRunResult(
        total_cases=3,
        passed_cases=1,
        failed_cases=2,
        pass_rate=1.0/3.0,
        case_results=(res_1, res_2, res_3),
        duration_ms=50.0
    )

    analysis_run = SQLFailureAnalyzer.analyze_run(run)
    counts = analysis_run.category_counts
    assert counts[SQLFailureCategory.PASSED] == 1
    assert counts[SQLFailureCategory.EMPTY_PREDICTED_SQL] == 1
    assert counts[SQLFailureCategory.ROW_COUNT_MISMATCH] == 1
    assert counts[SQLFailureCategory.SQL_EXECUTION_ERROR] == 0


def test_analyzer_invalid_arguments_raise_error():
    with pytest.raises(SQLFailureAnalyticsContractError):
        SQLFailureAnalyzer.analyze_case("invalid_input")  # type: ignore

    with pytest.raises(SQLFailureAnalyticsContractError):
        SQLFailureAnalyzer.analyze_run("invalid_input")  # type: ignore
