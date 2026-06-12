import json
import os
import sqlite3
import pytest

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures")
SEED_SQL_PATH = os.path.join(FIXTURES_DIR, "execution_result", "execution_result_seed.sql")
GOLDEN_CASES_PATH = os.path.join(FIXTURES_DIR, "execution_result", "execution_result_golden_cases.json")


def load_seed_sql() -> str:
    with open(SEED_SQL_PATH, "r", encoding="utf-8") as f:
        return f.read()


def load_golden_cases() -> list[dict]:
    with open(GOLDEN_CASES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def create_db(seed_sql: str) -> sqlite3.Connection:
    """
    Creates an in-memory SQLite database and executes the seed SQL script.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(seed_sql)
    return conn


def execute_query(conn: sqlite3.Connection, sql: str) -> list[dict]:
    """
    Executes the given SQL query on the database connection and returns rows as dictionaries.
    """
    cursor = conn.execute(sql)
    return [dict(row) for row in cursor.fetchall()]


def compare_values(actual, expected) -> bool:
    """
    Compares two values, allowing for a numeric floating point tolerance of 1e-6.
    """
    # Try direct comparison
    if actual == expected:
        return True

    # Try numeric conversion and epsilon check
    try:
        act_val = float(actual)
        exp_val = float(expected)
        return abs(act_val - exp_val) < 1e-6
    except (ValueError, TypeError):
        pass

    # Fallback to string comparison
    return str(actual) == str(expected)


def compare_row(actual: dict, expected: dict) -> bool:
    """
    Compares two row dictionaries key by key.
    """
    if set(actual.keys()) != set(expected.keys()):
        return False
    for key in expected:
        if not compare_values(actual[key], expected[key]):
            return False
    return True


def assert_rows_match(actual: list[dict], expected: list[dict], ordered: bool, case_id: str):
    """
    Asserts that the actual rows match the expected rows under ordered or unordered semantics,
    providing highly descriptive error messages containing the case_id.
    """
    assert len(actual) == len(expected), (
        f"Case '{case_id}': Row count mismatch. Expected {len(expected)}, got {len(actual)}.\n"
        f"Expected: {expected}\n"
        f"Actual: {actual}"
    )

    if ordered:
        for idx, (act, exp) in enumerate(zip(actual, expected)):
            assert compare_row(act, exp), (
                f"Case '{case_id}': Row mismatch at index {idx} under ordered comparison.\n"
                f"Expected: {exp}\n"
                f"Actual: {act}"
            )
    else:
        remaining_actual = list(actual)
        for exp in expected:
            matched = False
            for act in remaining_actual:
                if compare_row(act, exp):
                    remaining_actual.remove(act)
                    matched = True
                    break
            assert matched, (
                f"Case '{case_id}': Expected row {exp} not found in actual results under unordered comparison.\n"
                f"Expected: {expected}\n"
                f"Actual: {actual}"
            )


@pytest.fixture(scope="module")
def db_conn():
    """
    Fixture providing a populated in-memory SQLite connection.
    """
    seed_sql = load_seed_sql()
    conn = create_db(seed_sql)
    yield conn
    conn.close()


@pytest.mark.parametrize("case", load_golden_cases(), ids=lambda c: c["id"])
def test_execution_result_correctness(db_conn, case):
    """
    Verifies that the golden SQL returns the exact expected rows when executed against the seed DB.
    """
    case_id = case["id"]
    sql = case["sql"]
    expected_rows = case["expected_rows"]
    ordered = case.get("ordered", True)

    try:
        actual_rows = execute_query(db_conn, sql)
    except Exception as e:
        pytest.fail(f"Case '{case_id}': Failed to execute query. Error: {e}\nSQL: {sql}")

    assert_rows_match(actual_rows, expected_rows, ordered, case_id)
