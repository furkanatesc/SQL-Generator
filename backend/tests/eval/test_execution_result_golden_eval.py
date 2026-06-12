import json
import os
import pytest

from tests.eval.eval_helpers import create_db, execute_query, assert_rows_match

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures")
SEED_SQL_PATH = os.path.join(FIXTURES_DIR, "execution_result", "execution_result_seed.sql")
GOLDEN_CASES_PATH = os.path.join(FIXTURES_DIR, "execution_result", "execution_result_golden_cases.json")


def load_seed_sql() -> str:
    with open(SEED_SQL_PATH, "r", encoding="utf-8") as f:
        return f.read()


def load_golden_cases() -> list[dict]:
    with open(GOLDEN_CASES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)



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
