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
    SQLFailureAnalyzerConfig,
    SQLFailureCategoryCount,
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


def test_sql_failure_analyzer_config():
    config = SQLFailureAnalyzerConfig(
        include_zero_count_categories=False,
        include_warning_signals=False
    )
    assert config.include_zero_count_categories is False
    assert config.include_warning_signals is False


def test_failure_analysis_result_is_frozen():
    res = SQLFailureAnalysisResult(
        case_id="c1",
        category=SQLFailureCategory.PASSED,
        severity=SQLFailureSeverity.INFO,
        passed=True,
        evidence="passed"
    )
    with pytest.raises((FrozenInstanceError, AttributeError)):
        res.category = SQLFailureCategory.UNKNOWN_FAILURE  # type: ignore


def test_failure_analytics_run_result_category_counts_are_immutable():
    counts = (SQLFailureCategoryCount(SQLFailureCategory.PASSED, 1),)
    run = SQLFailureAnalyticsRunResult(
        total_cases=1,
        passed_cases=1,
        failed_cases=0,
        pass_rate=1.0,
        category_counts=counts,
        case_results=(),
        duration_ms=10.0
    )
    with pytest.raises((FrozenInstanceError, AttributeError)):
        run.category_counts = ()  # type: ignore


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


def test_analyzer_detects_column_shape_mismatch_beyond_first_row():
    # Columns are identical on first row, but second row differs
    res = make_mock_case_result(
        passed=False,
        expected_row_count=2,
        actual_row_count=2,
        normalized_expected_result=[{"id": 1}, {"id": 2, "name": "Bob"}],
        normalized_actual_result=[{"id": 1}, {"id": 2, "score": 80}],
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
    
    # Locate counts
    passed_count = next(c.count for c in analysis_run.category_counts if c.category == SQLFailureCategory.PASSED)
    empty_sql_count = next(c.count for c in analysis_run.category_counts if c.category == SQLFailureCategory.EMPTY_PREDICTED_SQL)
    row_count_mismatch_count = next(c.count for c in analysis_run.category_counts if c.category == SQLFailureCategory.ROW_COUNT_MISMATCH)
    sql_error_count = next(c.count for c in analysis_run.category_counts if c.category == SQLFailureCategory.SQL_EXECUTION_ERROR)

    assert passed_count == 1
    assert empty_sql_count == 1
    assert row_count_mismatch_count == 1
    assert sql_error_count == 0


def test_analyzer_invalid_arguments_raise_error():
    with pytest.raises(SQLFailureAnalyticsContractError):
        SQLFailureAnalyzer.analyze_case("invalid_input")  # type: ignore

    with pytest.raises(SQLFailureAnalyticsContractError):
        SQLFailureAnalyzer.analyze_run("invalid_input")  # type: ignore


# --- Dataclass Parameter Validation Tests ---

def test_failure_analysis_result_rejects_empty_case_id():
    with pytest.raises(SQLFailureAnalyticsContractError) as exc:
        SQLFailureAnalysisResult(
            case_id="",
            category=SQLFailureCategory.PASSED,
            severity=SQLFailureSeverity.INFO,
            passed=True,
            evidence="passed"
        )
    assert "case_id cannot be empty" in str(exc.value)


def test_failure_analysis_result_rejects_invalid_category():
    with pytest.raises(SQLFailureAnalyticsContractError) as exc:
        SQLFailureAnalysisResult(
            case_id="c1",
            category="invalid_category",  # type: ignore
            severity=SQLFailureSeverity.INFO,
            passed=True,
            evidence="passed"
        )
    assert "Invalid category" in str(exc.value)


def test_failure_analysis_result_rejects_invalid_severity():
    with pytest.raises(SQLFailureAnalyticsContractError) as exc:
        SQLFailureAnalysisResult(
            case_id="c1",
            category=SQLFailureCategory.PASSED,
            severity="wat",  # type: ignore
            passed=True,
            evidence="passed"
        )
    assert "Invalid severity" in str(exc.value)


def test_failure_analysis_result_rejects_empty_evidence():
    with pytest.raises(SQLFailureAnalyticsContractError) as exc:
        SQLFailureAnalysisResult(
            case_id="c1",
            category=SQLFailureCategory.PASSED,
            severity=SQLFailureSeverity.INFO,
            passed=True,
            evidence="  "
        )
    assert "evidence cannot be empty" in str(exc.value)


def test_failure_analysis_result_rejects_non_signal_items():
    with pytest.raises(SQLFailureAnalyticsContractError) as exc:
        SQLFailureAnalysisResult(
            case_id="c1",
            category=SQLFailureCategory.PASSED,
            severity=SQLFailureSeverity.INFO,
            passed=True,
            evidence="passed",
            signals=("not_a_signal_obj",)  # type: ignore
        )
    assert "All signals must be instances of SQLFailureSignal" in str(exc.value)


# --- Sprint 25.5 Tests ---

def test_execution_accuracy_failure_analysis_maps_sqlite_execution_error():
    res = make_mock_case_result(
        passed=False,
        execution_error="no such table: users"
    )
    analysis = SQLFailureAnalyzer.analyze_case(res)
    assert analysis.passed is False
    assert analysis.category == SQLFailureCategory.SQL_EXECUTION_ERROR
    assert analysis.severity == SQLFailureSeverity.MEDIUM
    assert "no such table: users" in analysis.evidence


def test_execution_accuracy_failure_analysis_maps_blocked_live_connection():
    res = make_mock_case_result(
        passed=False,
        execution_error="blocked_live_connection"
    )
    analysis = SQLFailureAnalyzer.analyze_case(res)
    assert analysis.passed is False
    assert analysis.category == SQLFailureCategory.BLOCKED_LIVE_CONNECTION
    assert analysis.severity == SQLFailureSeverity.CRITICAL
    assert "blocked by policy" in analysis.evidence


def test_execution_accuracy_failure_analysis_maps_rejected_orchestrator_outcome():
    res1 = make_mock_case_result(
        passed=False,
        execution_error="rejected_by_orchestrator: complexity limit exceeded"
    )
    analysis1 = SQLFailureAnalyzer.analyze_case(res1)
    assert analysis1.passed is False
    assert analysis1.category == SQLFailureCategory.REJECTED_BY_ORCHESTRATOR
    assert analysis1.severity == SQLFailureSeverity.HIGH
    assert "complexity limit exceeded" in analysis1.evidence

    res2 = make_mock_case_result(
        passed=False,
        execution_error="rejected"
    )
    analysis2 = SQLFailureAnalyzer.analyze_case(res2)
    assert analysis2.passed is False
    assert analysis2.category == SQLFailureCategory.REJECTED_BY_ORCHESTRATOR
    assert analysis2.severity == SQLFailureSeverity.HIGH


def test_execution_accuracy_failure_analysis_ignores_successful_execution():
    res = make_mock_case_result(
        passed=True,
        execution_error="some ignored error string"
    )
    analysis = SQLFailureAnalyzer.analyze_case(res)
    assert analysis.passed is True
    assert analysis.category == SQLFailureCategory.PASSED
    assert analysis.severity == SQLFailureSeverity.INFO


def test_execution_accuracy_failure_analysis_does_not_leak_connection_ref_or_secret():
    res = make_mock_case_result(
        passed=False,
        fixture_ref="prod-postgres-main",
        execution_error="Failed to connect to prod-postgres-main: password: secret123; api_key=xyz987; Bearer tkn456; postgres://user:mysecretpwd@host/db?sslmode=require"
    )
    analysis = SQLFailureAnalyzer.analyze_case(res)
    assert "prod-postgres-main" not in analysis.evidence
    assert "secret123" not in analysis.evidence
    assert "xyz987" not in analysis.evidence
    assert "tkn456" not in analysis.evidence
    assert "mysecretpwd" not in analysis.evidence
    
    assert "[REDACTED_CONNECTION]" in analysis.evidence
    assert "password:[REDACTED]" in analysis.evidence
    assert "api_key=[REDACTED]" in analysis.evidence
    assert "Bearer [REDACTED]" in analysis.evidence
    assert "postgres://user:[REDACTED]@host" in analysis.evidence


def test_execution_accuracy_failure_analysis_does_not_import_network_or_db_drivers():
    import subprocess
    import sys
    code = (
        "import sys\n"
        "import app.evaluation.failure_analytics\n"
        "forbidden = ['psycopg', 'psycopg2', 'oracledb', 'cx_Oracle', 'pymysql', 'pyodbc', 'mysql']\n"
        "for mod in forbidden:\n"
        "    if mod in sys.modules:\n"
        "        print(f'FORBIDDEN:{mod}')\n"
    )
    res = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True
    )
    assert "FORBIDDEN" not in res.stdout, f"Importing failure_analytics imported forbidden driver: {res.stdout}"


def test_execution_accuracy_failure_analysis_preserves_deterministic_category():
    res = make_mock_case_result(
        passed=False,
        execution_error="predicted_sql cannot be empty"
    )
    analysis = SQLFailureAnalyzer.analyze_case(res)
    assert analysis.category == SQLFailureCategory.EMPTY_PREDICTED_SQL


def test_execution_accuracy_failure_analysis_rejected_orchestrator_integration():
    from app.evaluation.execution_accuracy import SQLExecutionAccuracyConfig, SQLExecutionAccuracyHarness
    from app.evaluation.connection_aware_execution_orchestrator import SQLConnectionAwareExecutionOrchestrator, SQLConnectionAwareExecutionOutcome, SQLConnectionAwareExecutionOutcomeStatus
    from app.evaluation.multi_database_execution import SQLDatabaseExecutionRequest
    from app.evaluation.golden_dataset_contract import SQLGoldenDatasetCase, SQLResultComparePolicy, SQLGoldenDatasetTier, SQLAdjudicationStatus
    
    class StubRejectedOrchestrator(SQLConnectionAwareExecutionOrchestrator):
        def __init__(self):
            pass
        def execute(self, request: SQLDatabaseExecutionRequest):
            return SQLConnectionAwareExecutionOutcome(
                version="sql_connection_aware_execution_orchestrator_v1",
                request=request,
                plan=None,
                status=SQLConnectionAwareExecutionOutcomeStatus.REJECTED,
                execution_result=None,
                error="Local execution is not supported for dialect: postgresql",
                warnings=(),
            )
            
    config = SQLExecutionAccuracyConfig(fixtures_dir="data")
    harness = SQLExecutionAccuracyHarness(config, orchestrator=StubRejectedOrchestrator())
    
    case = SQLGoldenDatasetCase(
        case_id="integration_reject_test",
        question="Get all data",
        dialect="postgresql",
        schema_snapshot_id="snap",
        fixture_ref="db_ref",
        gold_sql="SELECT 1",
        tier=SQLGoldenDatasetTier.CORE_REGRESSION,
        adjudication_status=SQLAdjudicationStatus.APPROVED,
        no_expected_result_reason="Run reference gold_sql",
        result_compare_policy=SQLResultComparePolicy.EXACT_UNORDERED,
    )
    case_result = harness.run_case(case, "SELECT 1")
    
    assert case_result.passed is False
    assert case_result.execution_error == "rejected_by_orchestrator: Local execution is not supported for dialect: postgresql"
    
    analysis = SQLFailureAnalyzer.analyze_case(case_result)
    assert analysis.passed is False
    assert analysis.category == SQLFailureCategory.REJECTED_BY_ORCHESTRATOR
    assert analysis.severity == SQLFailureSeverity.HIGH
    assert "Local execution is not supported for dialect: postgresql" in analysis.evidence

