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
    Compares two values, allowing for a numeric floating point tolerance of 1e-6
    without generic type coercion to string.
    """
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return abs(float(actual) - float(expected)) < 1e-6
    return actual == expected


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


def test_execution_result_golden_cases_have_unique_ids():
    """
    Verifies that all execution result golden cases have unique identifiers.
    """
    cases = load_golden_cases()
    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids)), f"Duplicate case IDs found: {ids}"


def test_execution_result_seed_sql_loads():
    """
    Verifies that the seed SQL script executes successfully and creates all expected tables.
    """
    seed_sql = load_seed_sql()
    conn = create_db(seed_sql)
    try:
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        table_names = {row["name"] for row in tables}
        expected_tables = {
            "customers", "orders", "payments", "products",
            "order_items", "users", "audit_logs", "support_tickets"
        }
        assert expected_tables <= table_names, f"Missing expected tables: {expected_tables - table_names}"
    finally:
        conn.close()


def test_execution_result_golden_cases_have_required_fields():
    """
    Verifies that each golden case contains all required schema fields and correct types.
    """
    required = {"id", "question", "sql", "expected_rows", "ordered"}
    for case in load_golden_cases():
        assert required <= set(case), f"Case '{case.get('id')}' is missing required fields."
        assert isinstance(case["expected_rows"], list), f"expected_rows must be a list in case '{case.get('id')}'."
