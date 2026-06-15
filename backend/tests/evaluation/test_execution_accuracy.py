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


def test_comparator_null_normalization():
    # Standardize string "None", case-insensitive "NULL", and None
    actual = [{"name": "Alice", "score": "NULL"}, {"name": "Bob", "score": "none"}]
    expected = [{"name": "Alice", "score": None}, {"name": "Bob", "score": None}]
    assert SQLExecutionResultComparator.compare(
        actual, expected, SQLResultComparePolicy.EXACT_ORDERED, order_sensitive=True
    )


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
