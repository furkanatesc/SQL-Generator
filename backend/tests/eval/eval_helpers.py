import re
import sqlite3

def normalize_sql(sql: str) -> str:
    """
    Normalizes SQL string to make structural fragment comparisons robust.
    Removes quotes, normalizes spacing, and eliminates spaces around delimiters.
    """
    if not sql:
        return ""
    s = sql.lower()
    s = re.sub(r'[`"\[\]]', '', s)
    s = " ".join(s.split())
    s = re.sub(r'\s*(->)\s*', r'\1', s)
    s = re.sub(r'\s*([=,.<>()+/*;>-])\s*', r'\1', s)
    return s.strip()


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
