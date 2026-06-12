import json
import os
import re
import sqlite3
import pytest
from unittest.mock import patch, MagicMock

from app.sql_pipeline import SQLGenerationPipeline
from app.llm.provider import LLMProvider, SQLGenerationRequest, SQLGenerationResponse

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures")
SEED_SQL_PATH = os.path.join(FIXTURES_DIR, "execution_result", "execution_result_seed.sql")
GOLDEN_SCHEMA_PATH = os.path.join(FIXTURES_DIR, "schema", "context_selection_golden_schema.json")
E2E_CASES_PATH = os.path.join(FIXTURES_DIR, "e2e", "e2e_golden_cases.json")


def load_seed_sql() -> str:
    with open(SEED_SQL_PATH, "r", encoding="utf-8") as f:
        return f.read()


def load_golden_schema() -> dict:
    with open(GOLDEN_SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def load_e2e_cases() -> list[dict]:
    with open(E2E_CASES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_sql(sql: str) -> str:
    """
    Normalizes SQL string to make structural fragment comparisons robust.
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


class E2EFakeLLMProvider(LLMProvider):
    """
    Deterministic fake LLM provider that yields preconfigured E2E SQL responses.
    Asserts that the question is in the prompt to verify no prompt mismatches.
    """
    def __init__(self, case: dict):
        self.case = case
        self.requests: list[SQLGenerationRequest] = []
        self.call_count = 0

    def generate_sql(self, request: SQLGenerationRequest) -> SQLGenerationResponse:
        self.requests.append(request)

        if self.case["question"] not in request.prompt:
            raise AssertionError(
                f"E2EFakeLLMProvider prompt does not contain case question: {self.case['id']}"
            )

        responses = self.case["fake_sql_responses"]
        sql = responses[min(self.call_count, len(responses) - 1)]
        self.call_count += 1

        return SQLGenerationResponse(
            sql=sql,
            provider_name="e2e-fake",
            model_name="deterministic-fake",
            raw_output=sql,
            metadata={
                "dialect": request.dialect,
                "purpose": request.purpose,
            }
        )


def compare_values(actual, expected) -> bool:
    """
    Compares two values with numeric tolerance of 1e-6 without generic type coercion.
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
    Asserts that actual rows match expected rows with detailed error messages containing case_id.
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


@pytest.fixture(scope="module")
def golden_schema():
    return load_golden_schema()


@pytest.mark.parametrize("case", load_e2e_cases(), ids=lambda c: c["id"])
def test_e2e_golden_pipeline_to_execution(db_conn, golden_schema, case):
    """
    Performs E2E simulation: runs pipeline -> retrieves SQL -> executes on SQLite -> asserts correct rows.
    """
    case_id = case["id"]
    question = case["question"]
    expected_rows = case["expected_rows"]
    ordered = case.get("ordered", True)
    expected_tables = case.get("expected_tables", [])
    forbidden_tables = case.get("forbidden_tables", [])

    # 1. Setup deterministic fake LLM provider and initialize pipeline
    fake_provider = E2EFakeLLMProvider(case)
    pipeline = SQLGenerationPipeline(llm_provider=fake_provider)

    # Mock RAG to return the expected tables to simulate schema context selection
    def mock_search_ddl(query_text, limit=10, api_key=None):
        return [{"payload": {"table_name": tbl}, "score": 1.0} for tbl in expected_tables]

    with patch("app.schema_manager.SchemaManager.load_schema", return_value=golden_schema), \
         patch("app.rag_manager.RAGManager") as mock_rag_class:

        mock_rag_instance = MagicMock()
        mock_rag_instance.search_ddl.side_effect = mock_search_ddl
        mock_rag_class.return_value = mock_rag_instance

        # 2. Run the SQL Generation Pipeline
        result = pipeline.run_pipeline(
            natural_query=question,
            max_attempts=case.get("max_attempts", 1)
        )

    # 3. Verify pipeline outcomes
    assert result["success"] is True, f"Case '{case_id}': Pipeline failed with error: {result.get('error')}"
    assert result["generated_sql"], f"Case '{case_id}': Pipeline succeeded but generated_sql is empty."
    assert len(fake_provider.requests) > 0, f"Case '{case_id}': No prompts were sent to the LLM provider."

    generated_sql = result["generated_sql"]
    normalized_generated_sql = normalize_sql(generated_sql)

    # 4. Verify SQL contracts (expected and forbidden tables)
    for tbl in expected_tables:
        assert tbl in normalized_generated_sql, (
            f"Case '{case_id}': Expected table '{tbl}' was not found in the final SQL: {generated_sql}"
        )

    for tbl in forbidden_tables:
        assert tbl not in normalized_generated_sql, (
            f"Case '{case_id}': Forbidden table '{tbl}' was found in the final SQL: {generated_sql}"
        )

    # 5. Execute the final generated SQL and compare actual vs expected rows
    try:
        actual_rows = execute_query(db_conn, generated_sql)
    except Exception as e:
        pytest.fail(f"Case '{case_id}': Failed to execute final generated SQL on SQLite. Error: {e}\nSQL: {generated_sql}")

    assert_rows_match(actual_rows, expected_rows, ordered, case_id)


def test_e2e_golden_cases_have_unique_ids():
    """
    Verifies that all E2E cases have unique identifiers.
    """
    cases = load_e2e_cases()
    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids)), f"Duplicate E2E case IDs found: {ids}"


def test_e2e_golden_cases_have_required_fields():
    """
    Verifies that each E2E case contains all required properties and correct types.
    """
    required = {"id", "question", "fake_sql_responses", "expected_rows", "ordered", "expected_tables", "forbidden_tables"}
    for case in load_e2e_cases():
        assert required <= set(case), f"E2E Case '{case.get('id')}' is missing required fields."
        assert isinstance(case["fake_sql_responses"], list), f"fake_sql_responses must be a list in E2E case '{case.get('id')}'."
        assert isinstance(case["expected_rows"], list), f"expected_rows must be a list in E2E case '{case.get('id')}'."
