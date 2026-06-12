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
    each golden test case based on query matching. Raises AssertionError if the case
    cannot be matched to prevent masking context selection bugs.
    """
    def __init__(self, cases: list[dict]):
        self.responses_by_question = {}
        for case in cases:
            q = case["question"]
            self.responses_by_question[q] = list(case.get("sql_responses", []))
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
            raise AssertionError(
                f"GoldenFakeLLMProvider could not map prompt to a golden case. "
                f"Prompt excerpt: {request.prompt[:500]}"
            )
            
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


def run_case_pipeline(case: dict, golden_schema: dict):
    """
    Helper to configure patches and run the SQL Generation Pipeline for a single case.
    """
    fake_provider = GoldenFakeLLMProvider([case])
    pipeline = SQLGenerationPipeline(llm_provider=fake_provider)

    # Mock RAG search to retrieve expected tables
    def mock_search_ddl(query_text, limit=10, api_key=None):
        return [{"payload": {"table_name": tbl}, "score": 1.0} for tbl in case["expected_tables"]]

    with patch("app.schema_manager.SchemaManager.load_schema", return_value=golden_schema), \
         patch("app.rag_manager.RAGManager") as mock_rag_class:
         
        mock_rag_instance = MagicMock()
        mock_rag_instance.search_ddl.side_effect = mock_search_ddl
        mock_rag_class.return_value = mock_rag_instance

        result = pipeline.run_pipeline(
            natural_query=case["question"],
            max_attempts=case["max_attempts"]
        )
        
    return result, fake_provider


def test_golden_cases_unique_ids():
    cases = load_json(GOLDEN_CASES_PATH)
    ids = [case["id"] for case in cases]
    assert len(ids) == len(set(ids)), "Golden cases must have unique IDs"


@pytest.mark.parametrize("case", load_json(GOLDEN_CASES_PATH), ids=lambda c: c["id"])
def test_sql_generation_prompt_context(case, golden_schema):
    """
    Asserts that correct context is selected and formatted into the prompt
    passed to the LLM (verifies table recall, table exclusion, and relationship serialization).
    """
    result, fake_provider = run_case_pipeline(case, golden_schema)
    
    assert result["success"] is True, \
        f"Case '{case['id']}': Pipeline failed: {result.get('error')}"
    
    assert len(fake_provider.requests) > 0, \
        f"Case '{case['id']}': No generation requests made to fake provider"

    # Verify context in all prompts sent (e.g. writer and corrector prompts)
    for idx, req in enumerate(fake_provider.requests):
        prompt = req.prompt
        normalized_prompt = normalize_sql(prompt)

        # 1. Required prompt tables must exist in prompt context (with word boundaries)
        for tbl in case["required_prompt_tables"]:
            assert re.search(r"\b" + re.escape(tbl.lower()) + r"\b", normalized_prompt), \
                f"Case '{case['id']}' (Request {idx}): Required table '{tbl}' not found in prompt context: {prompt}"

        # 2. Forbidden prompt tables must not exist in prompt context
        for tbl in case["forbidden_prompt_tables"]:
            assert not re.search(r"\b" + re.escape(tbl.lower()) + r"\b", normalized_prompt), \
                f"Case '{case['id']}' (Request {idx}): Forbidden table '{tbl}' found in prompt context: {prompt}"

        # 3. Required relationships must be serialized in prompt context
        for edge in case["required_prompt_edges"]:
            col, ref_table = edge
            found = False
            for line in prompt.lower().splitlines():
                if col.lower() in line and ref_table.lower() in line:
                    found = True
                    break
            assert found, \
                f"Case '{case['id']}' (Request {idx}): Relationship edge '{col} -> {ref_table}' not found in prompt context: {prompt}"


@pytest.mark.parametrize("case", load_json(GOLDEN_CASES_PATH), ids=lambda c: c["id"])
def test_sql_generation_sql_correctness(case, golden_schema):
    """
    Asserts that the final generated SQL respects expected structure contracts
    (expected/forbidden tables, required joins, expected column projections, etc.).
    """
    result, _ = run_case_pipeline(case, golden_schema)
    
    assert result["success"] is True, \
        f"Case '{case['id']}': Pipeline failed: {result.get('error')}"

    generated_sql = result["generated_sql"]
    assert generated_sql, f"Case '{case['id']}': Generated SQL is empty"

    normalized_sql = normalize_sql(generated_sql)

    # 1. Expected tables in SQL (with word boundaries)
    for tbl in case["expected_tables"]:
        assert re.search(r"\b" + re.escape(tbl.lower()) + r"\b", normalized_sql), \
            f"Case '{case['id']}': Expected table '{tbl}' not found in SQL: {generated_sql}"

    # 2. Forbidden tables NOT in SQL (with word boundaries)
    for tbl in case["forbidden_tables"]:
        assert not re.search(r"\b" + re.escape(tbl.lower()) + r"\b", normalized_sql), \
            f"Case '{case['id']}': Forbidden table '{tbl}' was found in SQL: {generated_sql}"

    # 3. Required SQL fragments (e.g. joins, filters)
    for fragment in case["required_sql_fragments"]:
        norm_frag = normalize_sql(fragment)
        assert norm_frag in normalized_sql, \
            f"Case '{case['id']}': Required fragment '{fragment}' (normalized: '{norm_frag}') not found in SQL: {generated_sql}"

    # 4. Forbidden SQL fragments (e.g. SELECT *, wrong columns)
    for fragment in case["forbidden_sql_fragments"]:
        norm_frag = normalize_sql(fragment)
        assert norm_frag not in normalized_sql, \
            f"Case '{case['id']}': Forbidden fragment '{fragment}' (normalized: '{norm_frag}') was found in SQL: {generated_sql}"

    # 5. Expected columns projected
    for col in case["expected_columns"]:
        norm_col = normalize_sql(col)
        assert norm_col in normalized_sql, \
            f"Case '{case['id']}': Expected column/expression '{col}' (normalized: '{norm_col}') not found in SQL: {generated_sql}"


@pytest.mark.parametrize("case", load_json(GOLDEN_CASES_PATH), ids=lambda c: c["id"])
def test_sql_generation_validator_compatibility(case, golden_schema):
    """
    Asserts that the final SQL query passes standard semantic and dialect validation rules.
    """
    result, _ = run_case_pipeline(case, golden_schema)
    
    assert result["success"] is True, \
        f"Case '{case['id']}': Pipeline failed: {result.get('error')}"

    generated_sql = result["generated_sql"]
    assert generated_sql, f"Case '{case['id']}': Generated SQL is empty"

    valid, error = SQLValidator.validate(generated_sql, golden_schema)
    assert valid is True, \
        f"Case '{case['id']}': Generated SQL failed semantic validation: {error}. Query: {generated_sql}"
