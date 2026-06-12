import json
import os
import re
import pytest
from unittest.mock import patch, MagicMock

from app.sql_pipeline import SQLGenerationPipeline
from app.llm.provider import LLMProvider, SQLGenerationRequest, SQLGenerationResponse
from app.sql_validator import SQLValidator

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures")
GOLDEN_SCHEMA_PATH = os.path.join(FIXTURES_DIR, "schema", "context_selection_golden_schema.json")
GOLDEN_CASES_PATH = os.path.join(FIXTURES_DIR, "sql_generation", "sql_generation_golden_cases.json")


def load_json(path: str) -> dict | list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_sql(sql: str) -> str:
    """
    Normalizes SQL string to make structural fragment comparisons robust.
    Removes quotes, normalizes spacing, and eliminates spaces around delimiters.
    """
    if not sql:
        return ""
    # Convert to lowercase
    s = sql.lower()
    # Remove quotes, backticks, brackets
    s = re.sub(r'[`"\[\]]', '', s)
    # Replace all whitespace sequences with a single space
    s = " ".join(s.split())
    # Remove spaces around common operators and punctuation
    s = re.sub(r'\s*([=,.<>()+/*;-])\s*', r'\1', s)
    return s.strip()


class GoldenFakeLLMProvider(LLMProvider):
    """
    Fake LLM provider that yields deterministic, pre-configured SQL responses for
    each golden test case based on query matching. Supports multiple attempts to test
    critic/corrector loops.
    """
    def __init__(self, cases: list[dict]):
        self.responses_by_question = {}
        for case in cases:
            q = case["question"]
            responses = case.get("sql_responses", [])
            self.responses_by_question[q] = list(responses)
        self.call_counts = {}
        self.requests: list[SQLGenerationRequest] = []

    def generate_sql(self, request: SQLGenerationRequest) -> SQLGenerationResponse:
        self.requests.append(request)
        
        # Find which case this request is for by checking if the question is in the prompt
        matched_q = None
        for q in self.responses_by_question:
            if q in request.prompt:
                matched_q = q
                break
                
        if not matched_q:
            # Fallback to the first case if not found
            matched_q = list(self.responses_by_question.keys())[0]
            
        responses = self.responses_by_question[matched_q]
        call_count = self.call_counts.get(matched_q, 0)
        
        if call_count < len(responses):
            sql = responses[call_count]
        else:
            sql = responses[-1]
            
        self.call_counts[matched_q] = call_count + 1
        
        return SQLGenerationResponse(
            sql=sql,
            provider_name="golden-fake",
            model_name="deterministic-fake",
            raw_output=sql,
            metadata={
                "dialect": request.dialect,
                "purpose": request.purpose,
            }
        )


@pytest.fixture(scope="module")
def golden_schema():
    return load_json(GOLDEN_SCHEMA_PATH)


@pytest.fixture(scope="module")
def golden_cases():
    return load_json(GOLDEN_CASES_PATH)


def test_golden_cases_unique_ids(golden_cases):
    ids = [case["id"] for case in golden_cases]
    assert len(ids) == len(set(ids)), "Golden cases must have unique IDs"


def test_sql_generation_golden_eval_gate(golden_schema, golden_cases):
    """
    Executes the golden evaluation gate for SQL generation behavior.
    Uses the real context selection/pruning and prompt serialization paths
    with a deterministic fake LLM provider.
    """
    fake_provider = GoldenFakeLLMProvider(golden_cases)
    pipeline = SQLGenerationPipeline(llm_provider=fake_provider)

    for case in golden_cases:
        case_id = case["id"]
        question = case["question"]
        expected_tables = case["expected_tables"]
        forbidden_tables = case["forbidden_tables"]
        required_fragments = case["required_sql_fragments"]
        forbidden_fragments = case["forbidden_sql_fragments"]
        expected_columns = case["expected_columns"]
        max_attempts = case["max_attempts"]

        # Mock RAG table search to return expected tables as retrieval hits
        def mock_search_ddl(query_text, limit=10, api_key=None):
            return [{"payload": {"table_name": tbl}, "score": 1.0} for tbl in expected_tables]

        with patch("app.schema_manager.SchemaManager.load_schema", return_value=golden_schema), \
             patch("app.rag_manager.RAGManager") as mock_rag_class:
             
            mock_rag_instance = MagicMock()
            mock_rag_instance.search_ddl.side_effect = mock_search_ddl
            mock_rag_class.return_value = mock_rag_instance

            # Run the generation pipeline
            result = pipeline.run_pipeline(
                natural_query=question,
                max_attempts=max_attempts
            )

            # 1. Pipeline success assertion
            assert result["success"] is True, \
                f"Case '{case_id}': Pipeline failed to generate SQL. Error: {result.get('error')}"
            
            generated_sql = result["generated_sql"]
            assert generated_sql, f"Case '{case_id}': Generated SQL string is empty"

            normalized_sql = normalize_sql(generated_sql)

            # 2. Required table assertions
            for tbl in expected_tables:
                assert tbl.lower() in normalized_sql, \
                    f"Case '{case_id}': Expected table '{tbl}' was not found in normalized SQL: {generated_sql}"

            # 3. Forbidden table assertions
            for tbl in forbidden_tables:
                # Use word boundaries to check if table is referenced in normalized SQL
                assert not re.search(r'\b' + re.escape(tbl.lower()) + r'\b', normalized_sql), \
                    f"Case '{case_id}': Forbidden table '{tbl}' was referenced in normalized SQL: {generated_sql}"

            # 4. Required SQL fragments (e.g. joins, filters)
            for fragment in required_fragments:
                norm_frag = normalize_sql(fragment)
                assert norm_frag in normalized_sql, \
                    f"Case '{case_id}': Required SQL fragment '{fragment}' (normalized: '{norm_frag}') not found in: {generated_sql}"

            # 5. Forbidden SQL fragments (e.g. SELECT *, wrong columns)
            for fragment in forbidden_fragments:
                norm_frag = normalize_sql(fragment)
                assert norm_frag not in normalized_sql, \
                    f"Case '{case_id}': Forbidden SQL fragment '{fragment}' (normalized: '{norm_frag}') was found in: {generated_sql}"

            # 6. Expected columns are present
            for col in expected_columns:
                norm_col = normalize_sql(col)
                assert norm_col in normalized_sql, \
                    f"Case '{case_id}': Expected column reference '{col}' (normalized: '{norm_col}') not found in: {generated_sql}"

            # 7. Semantic validation pass (Layer 1 + 5 validator)
            valid, error = SQLValidator.validate(generated_sql, golden_schema)
            assert valid is True, \
                f"Case '{case_id}': Generated SQL failed semantic validation: {error}. Query: {generated_sql}"
