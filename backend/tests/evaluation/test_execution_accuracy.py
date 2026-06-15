import os
import sqlite3
import tempfile
import pytest

from app.evaluation.golden_dataset_contract import (
    SQLGoldenDatasetCase,
    SQLResultComparePolicy,
    SQLGoldenDatasetTier,
    SQLAdjudicationStatus,
)
from app.evaluation.execution_accuracy import (
    SQLExecutionAccuracyConfig,
    SQLExecutionAccuracyHarness,
    SQLExecutionResultComparator,
    SQLExecutionAccuracyContractError,
)


@pytest.fixture
def temp_fixtures_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a mock sqlite database
        db_path = os.path.join(tmpdir, "test_db.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT, score REAL)")
        cursor.execute("INSERT INTO users (id, name, score) VALUES (1, 'Alice', 95.51)")
        cursor.execute("INSERT INTO users (id, name, score) VALUES (2, 'Bob', 80.0)")
        cursor.execute("INSERT INTO users (id, name, score) VALUES (3, 'Charlie', NULL)")
        conn.commit()
        conn.close()
        yield tmpdir


def make_test_case(**kwargs):
    default_args = {
        "case_id": "c1",
        "question": "Get all users",
        "dialect": "sqlite",
        "schema_snapshot_id": "snap1",
        "fixture_ref": "test_db",
        "gold_sql": "SELECT id, name, score FROM users ORDER BY id",
        "tier": SQLGoldenDatasetTier.CORE_REGRESSION,
        "adjudication_status": SQLAdjudicationStatus.APPROVED,
        "no_expected_result_reason": "Run reference gold_sql",
        "result_compare_policy": SQLResultComparePolicy.EXACT_ORDERED,
    }
    default_args.update(kwargs)
    return SQLGoldenDatasetCase(**default_args)


def test_config_validation():
    # 1. empty fixtures_dir raises
    with pytest.raises(SQLExecutionAccuracyContractError) as exc_info:
        SQLExecutionAccuracyConfig(fixtures_dir="")
    assert "fixtures_dir cannot be empty" in str(exc_info.value)

    # 2. invalid timeout_seconds raises
    with pytest.raises(SQLExecutionAccuracyContractError) as exc_info:
        SQLExecutionAccuracyConfig(fixtures_dir="data", timeout_seconds=-0.5)
    assert "timeout_seconds must be greater than 0" in str(exc_info.value)

    # 3. invalid max_rows raises
    with pytest.raises(SQLExecutionAccuracyContractError) as exc_info:
        SQLExecutionAccuracyConfig(fixtures_dir="data", max_rows=0)
    assert "max_rows must be greater than 0" in str(exc_info.value)


def test_harness_empty_predicted_sql_rejected(temp_fixtures_dir):
    config = SQLExecutionAccuracyConfig(fixtures_dir=temp_fixtures_dir)
    harness = SQLExecutionAccuracyHarness(config)
    case = make_test_case()

    # 1. Single run raises SQLExecutionAccuracyContractError
    with pytest.raises(SQLExecutionAccuracyContractError) as exc_info:
        harness.run_case(case, "")
    assert "predicted_sql cannot be empty" in str(exc_info.value)

    # 2. Batch run records a failed case result instead of crashing
    run_result = harness.run_harness([case], {"c1": ""})
    assert run_result.total_cases == 1
    assert run_result.passed_cases == 0
    assert run_result.case_results[0].passed is False
    assert run_result.case_results[0].execution_error == "predicted_sql cannot be empty"


def test_harness_unsafe_ddl_rejected(temp_fixtures_dir):
    config = SQLExecutionAccuracyConfig(fixtures_dir=temp_fixtures_dir)
    harness = SQLExecutionAccuracyHarness(config)
    case = make_test_case()

    case_result = harness.run_case(case, "DROP TABLE users")
    assert case_result.passed is False
    assert "Only read-only SELECT statements are allowed" in case_result.execution_error


def test_harness_missing_fixture_reports_error(temp_fixtures_dir):
    config = SQLExecutionAccuracyConfig(fixtures_dir=temp_fixtures_dir)
    harness = SQLExecutionAccuracyHarness(config)
    case = make_test_case(fixture_ref="nonexistent_db")

    case_result = harness.run_case(case, "SELECT * FROM users")
    assert case_result.passed is False
    assert "Fixture database not found" in case_result.execution_error


def test_harness_reject_fixture_path_traversal(temp_fixtures_dir):
    config = SQLExecutionAccuracyConfig(fixtures_dir=temp_fixtures_dir)
    harness = SQLExecutionAccuracyHarness(config)

    # 1. Direct call raises SQLExecutionAccuracyContractError
    with pytest.raises(SQLExecutionAccuracyContractError) as exc_info:
        harness._resolve_db_path("../../etc/passwd")
    assert "fixture_ref cannot escape fixtures_dir" in str(exc_info.value)

    # 2. Executing the case results in a failed result record
    case = make_test_case(fixture_ref="../../etc/passwd")
    case_result = harness.run_case(case, "SELECT * FROM users")
    assert case_result.passed is False
    assert "fixture_ref cannot escape fixtures_dir" in case_result.execution_error


def test_harness_rejects_absolute_fixture_ref(temp_fixtures_dir):
    config = SQLExecutionAccuracyConfig(fixtures_dir=temp_fixtures_dir)
    harness = SQLExecutionAccuracyHarness(config)

    # 1. Direct call raises SQLExecutionAccuracyContractError
    with pytest.raises(SQLExecutionAccuracyContractError) as exc_info:
        harness._resolve_db_path("/tmp/fixture_db")
    assert "fixture_ref must be relative to fixtures_dir" in str(exc_info.value)

    # 2. Executing the case results in a failed result record
    case = make_test_case(fixture_ref="/tmp/fixture_db")
    case_result = harness.run_case(case, "SELECT * FROM users")
    assert case_result.passed is False
    assert "fixture_ref must be relative to fixtures_dir" in case_result.execution_error


def test_comparator_exact_ordered():
    # Exact ordered compares index-by-index and is key-order independent
    actual = [{"name": "Alice", "id": 1}, {"name": "Bob", "id": 2}]
    expected = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
    assert SQLExecutionResultComparator.compare(
        actual, expected, SQLResultComparePolicy.EXACT_ORDERED, order_sensitive=True
    )

    # Ordering mismatch fails
    mismatch = [{"id": 2, "name": "Bob"}, {"id": 1, "name": "Alice"}]
    assert not SQLExecutionResultComparator.compare(
        actual, mismatch, SQLResultComparePolicy.EXACT_ORDERED, order_sensitive=True
    )


def test_comparator_exact_unordered():
    # Exact unordered ignores row order and key order
    actual = [{"name": "Alice", "id": 1}, {"name": "Bob", "id": 2}]
    expected = [{"id": 2, "name": "Bob"}, {"id": 1, "name": "Alice"}]
    assert SQLExecutionResultComparator.compare(
        actual, expected, SQLResultComparePolicy.EXACT_UNORDERED, order_sensitive=False
    )

    # Different number of rows fails
    mismatch = [{"id": 1, "name": "Alice"}]
    assert not SQLExecutionResultComparator.compare(
        actual, mismatch, SQLResultComparePolicy.EXACT_UNORDERED, order_sensitive=False
    )

    # Mismatched values fail
    mismatch_values = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Charlie"}]
    assert not SQLExecutionResultComparator.compare(
        actual, mismatch_values, SQLResultComparePolicy.EXACT_UNORDERED, order_sensitive=False
    )


def test_exact_unordered_handles_mixed_value_types_without_crashing():
    # Verify that different types under same key do not crash sorting in EXACT_UNORDERED
    actual = [{"x": 1}, {"x": "1"}]
    expected = [{"x": "1"}, {"x": 1}]
    # This should pass without raising a TypeError
    assert SQLExecutionResultComparator.compare(
        actual, expected, SQLResultComparePolicy.EXACT_UNORDERED, order_sensitive=False
    )


def test_comparator_numeric_tolerance():
    # 1. Absolute tolerance check
    actual = [{"score": 95.512}]
    expected = [{"score": 95.510}]
    
    # Within 0.01 tolerance -> pass
    assert SQLExecutionResultComparator.compare(
        actual, expected, SQLResultComparePolicy.NUMERIC_TOLERANCE,
        order_sensitive=True, tolerance_policy={"epsilon": 0.005}
    )

    # Outside 0.001 tolerance -> fail
    assert not SQLExecutionResultComparator.compare(
        actual, expected, SQLResultComparePolicy.NUMERIC_TOLERANCE,
        order_sensitive=True, tolerance_policy={"epsilon": 0.001}
    )

    # 2. Relative tolerance check
    # score1 = 1000.0, score2 = 1001.0 -> diff is 1.0. Relative diff is 1.0 / 1001.0 ~= 0.000999
    act_rel = [{"score": 1000.0}]
    exp_rel = [{"score": 1001.0}]
    assert SQLExecutionResultComparator.compare(
        act_rel, exp_rel, SQLResultComparePolicy.NUMERIC_TOLERANCE,
        order_sensitive=True, tolerance_policy={"epsilon": 0.002, "relative": True}
    )
    assert not SQLExecutionResultComparator.compare(
        act_rel, exp_rel, SQLResultComparePolicy.NUMERIC_TOLERANCE,
        order_sensitive=True, tolerance_policy={"epsilon": 0.0005, "relative": True}
    )

    # 3. Unordered matching with tolerance
    act_unord = [{"score": 100.0}, {"score": 200.0}]
    exp_unord = [{"score": 200.01}, {"score": 99.99}]
    assert SQLExecutionResultComparator.compare(
        act_unord, exp_unord, SQLResultComparePolicy.NUMERIC_TOLERANCE,
        order_sensitive=False, tolerance_policy={"epsilon": 0.02}
    )


def test_comparator_subset_allowed():
    actual = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}, {"id": 3, "name": "Charlie"}]
    
    # 1. Unordered subset -> pass
    expected_unord = [{"id": 3, "name": "Charlie"}, {"id": 1, "name": "Alice"}]
    assert SQLExecutionResultComparator.compare(
        actual, expected_unord, SQLResultComparePolicy.SUBSET_ALLOWED, order_sensitive=False
    )

    # 2. Ordered subset (subsequence) -> mismatch order fails
    expected_ord = [{"id": 3, "name": "Charlie"}, {"id": 1, "name": "Alice"}]
    assert not SQLExecutionResultComparator.compare(
        actual, expected_ord, SQLResultComparePolicy.SUBSET_ALLOWED, order_sensitive=True
    )

    # 3. Ordered subset correct order -> pass
    expected_ord_correct = [{"id": 1, "name": "Alice"}, {"id": 3, "name": "Charlie"}]
    assert SQLExecutionResultComparator.compare(
        actual, expected_ord_correct, SQLResultComparePolicy.SUBSET_ALLOWED, order_sensitive=True
    )


def test_comparator_distinguishes_null_from_literal_null_string():
    actual = [{"x": None}]
    expected = [{"x": "NULL"}]
    # Literal "NULL" string is NOT treated as actual database NULL (None)
    assert not SQLExecutionResultComparator.compare(
        actual, expected, SQLResultComparePolicy.EXACT_ORDERED, order_sensitive=True
    )


def test_comparator_rejects_invalid_policy():
    actual = [{"x": 1}]
    expected = [{"x": 1}]
    with pytest.raises(SQLExecutionAccuracyContractError) as exc_info:
        SQLExecutionResultComparator.compare(
            actual, expected, "invalid_policy", order_sensitive=False
        )
    assert "Invalid result comparison policy: invalid_policy" in str(exc_info.value)


def test_run_result_sorts_case_results_deterministically(temp_fixtures_dir):
    config = SQLExecutionAccuracyConfig(fixtures_dir=temp_fixtures_dir)
    harness = SQLExecutionAccuracyHarness(config)

    case_c = make_test_case(case_id="case_c")
    case_a = make_test_case(case_id="case_a")
    case_b = make_test_case(case_id="case_b")

    cases = [case_c, case_a, case_b]
    sql_mapping = {
        "case_c": "SELECT id, name, score FROM users ORDER BY id",
        "case_a": "SELECT id, name, score FROM users ORDER BY id",
        "case_b": "SELECT id, name, score FROM users ORDER BY id",
    }

    run_result = harness.run_harness(cases, sql_mapping)
    assert run_result.case_results[0].case_id == "case_a"
    assert run_result.case_results[1].case_id == "case_b"
    assert run_result.case_results[2].case_id == "case_c"


def test_harness_run_successful_case(temp_fixtures_dir):
    config = SQLExecutionAccuracyConfig(fixtures_dir=temp_fixtures_dir)
    harness = SQLExecutionAccuracyHarness(config)
    
    case = make_test_case()
    
    # Case with matching predicted SQL
    predicted_sql = "SELECT id, name, score FROM users ORDER BY id"
    result = harness.run_case(case, predicted_sql)
    
    assert result.passed is True
    assert result.execution_error is None
    assert result.actual_row_count == 3
    assert result.expected_row_count == 3
    assert len(result.normalized_actual_result) == 3
    # Verify values are canonicalized (Charlie's score is None)
    assert result.normalized_actual_result[2]["score"] is None
    assert result.duration_ms >= 0.0
    assert result.predicted_sql_sha256 != ""
    assert result.gold_sql_sha256 != ""
