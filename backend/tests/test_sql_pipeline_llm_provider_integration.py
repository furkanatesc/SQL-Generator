from unittest.mock import MagicMock, patch

from app.sql_pipeline import SQLGenerationPipeline
from app.llm.fake_provider import DeterministicFakeLLMProvider
from app.llm.provider import LLMProvider, SQLGenerationRequest, SQLGenerationResponse


class TrackingFakeProvider(LLMProvider):
    def __init__(self, responses: list[str]):
        self.responses = responses
        self.requests_received: list[SQLGenerationRequest] = []
        self.call_count = 0

    def generate_sql(self, request: SQLGenerationRequest) -> SQLGenerationResponse:
        self.requests_received.append(request)
        sql = self.responses[self.call_count] if self.call_count < len(self.responses) else self.responses[-1]
        self.call_count += 1
        return SQLGenerationResponse(
            sql=sql,
            provider_name="tracking-fake",
            model_name="fake",
            raw_output=sql,
            metadata={"dialect": request.dialect, "purpose": request.purpose}
        )


def get_mocked_pipeline(llm_provider=None, nvidia_client=None):
    mock_schema_manager = MagicMock()
    pipeline = SQLGenerationPipeline(
        schema_manager=mock_schema_manager,
        nvidia_client=nvidia_client,
        llm_provider=llm_provider
    )
    # Mock schema pruner to avoid real embedding API calls during test
    pipeline.schema_pruner = MagicMock()
    pipeline.schema_pruner.prune_schema.return_value = {"tables": {"customers": {}}}
    return pipeline


def test_pipeline_uses_injected_provider_instead_of_nvidia_client():
    mock_nvidia_client = MagicMock()
    fake_provider = DeterministicFakeLLMProvider(sql="SELECT * FROM customers")
    
    pipeline = get_mocked_pipeline(llm_provider=fake_provider, nvidia_client=mock_nvidia_client)
    
    result = pipeline.run_pipeline(natural_query="test query")
    
    assert result["success"] is True
    assert result["generated_sql"] == "SELECT\n  *\nFROM customers"
    mock_nvidia_client.generate_sql.assert_not_called()


def test_writer_and_corrector_purpose_contract():
    # İlk cevap invalid sql, ikinci cevap geçerli sql olsun.
    # Böylece pipeline critic loop'a girer.
    fake_provider = TrackingFakeProvider(
        responses=[
            "INVALID SQL STATEMENT", 
            "SELECT * FROM customers"
        ]
    )
    
    pipeline = get_mocked_pipeline(llm_provider=fake_provider)
    
    result = pipeline.run_pipeline(natural_query="test query")
    
    assert result["success"] is True
    assert result["generated_sql"] == "SELECT\n  *\nFROM customers"
    
    assert len(fake_provider.requests_received) >= 2
    assert [req.purpose for req in fake_provider.requests_received] == ["writer", "corrector"]


def test_legacy_nvidia_path_preserved():
    mock_nvidia_client = MagicMock()
    mock_nvidia_client.generate_sql.return_value = "SELECT * FROM customers"
    
    pipeline = get_mocked_pipeline(nvidia_client=mock_nvidia_client, llm_provider=None)
    
    result = pipeline.run_pipeline(natural_query="test query")
    
    assert result["success"] is True
    assert result["generated_sql"] == "SELECT\n  *\nFROM customers"
    mock_nvidia_client.generate_sql.assert_called_once()


def test_injected_provider_does_not_construct_nvidia_client():
    fake_provider = DeterministicFakeLLMProvider(sql="SELECT * FROM customers")

    with patch("app.sql_pipeline.NVIDIAClient") as nvidia_client_cls:
        pipeline = SQLGenerationPipeline(
            schema_manager=MagicMock(),
            llm_provider=fake_provider,
        )
        pipeline.schema_pruner = MagicMock()
        pipeline.schema_pruner.prune_schema.return_value = {
            "tables": {"customers": {}}
        }

        result = pipeline.run_pipeline(natural_query="test query")

    assert result["success"] is True
    nvidia_client_cls.assert_not_called()


def test_pipeline_rejects_unsafe_generated_sql():
    # Fake LLM provider continually generates unsafe SQL
    fake_provider = DeterministicFakeLLMProvider(sql="DROP TABLE users;")
    
    pipeline = get_mocked_pipeline(llm_provider=fake_provider)
    
    result = pipeline.run_pipeline(natural_query="test query")
    
    assert result["success"] is False
    assert result["error"] is not None
    # Verify the attempts show guardrail validation failures
    assert len(result["attempts"]) > 0
    for attempt in result["attempts"]:
        assert attempt["valid"] is False
        assert any(
            err.get("stage") == "sql_guardrail" 
            for err in attempt.get("validation_errors", [])
        )


def test_pipeline_does_not_call_real_llm_for_guardrail_failure():
    # Guarantee we are not hitting the real LLM by using the mock client and checking call count
    mock_nvidia_client = MagicMock()
    fake_provider = TrackingFakeProvider(
        responses=["DELETE FROM orders;"] * 5  # Enough responses for all retries
    )
    
    pipeline = get_mocked_pipeline(llm_provider=fake_provider, nvidia_client=mock_nvidia_client)
    
    result = pipeline.run_pipeline(natural_query="test query")
    
    assert result["success"] is False
    # Ensure real client was not invoked
    mock_nvidia_client.generate_sql.assert_not_called()
    # Ensure the fake provider was indeed invoked and rejected
    assert len(fake_provider.requests_received) > 0


def test_pipeline_does_not_expose_guardrail_rejected_sql_as_generated_sql():
    # Fake LLM provider returns unsafe command-like SQL
    unsafe_sql = "DROP TABLE users;"
    fake_provider = TrackingFakeProvider(
        responses=[unsafe_sql] * 5
    )
    
    pipeline = get_mocked_pipeline(llm_provider=fake_provider)
    
    result = pipeline.run_pipeline(natural_query="delete everything")
    
    # Assert pipeline fails
    assert result["success"] is False
    
    # Assert generated_sql is sanitized (empty/none), never containing the unsafe SQL payload
    assert result["generated_sql"] == ""
    assert "DROP" not in result["generated_sql"]
    
    # Assert diagnostic details are retained
    last_attempt = result["attempts"][-1]
    assert last_attempt["sql"] == unsafe_sql
    assert any(err.get("stage") == "sql_guardrail" for err in last_attempt.get("validation_errors", []))


def test_pipeline_exposes_sql_on_non_guardrail_failure():
    # Fake LLM provider returns safe SQL but with syntax/semantic errors
    # For example, selecting from a non-existent table not in schema
    invalid_sql = "SELECT * FROM non_existent_table_12345"
    fake_provider = TrackingFakeProvider(
        responses=[invalid_sql] * 5
    )
    
    pipeline = get_mocked_pipeline(llm_provider=fake_provider)
    
    result = pipeline.run_pipeline(natural_query="get everything")
    
    # Assert pipeline fails
    assert result["success"] is False
    
    # Assert generated_sql still exposes the last attempted query for non-guardrail failures
    assert result["generated_sql"] == invalid_sql
    
    # Ensure it was NOT a guardrail failure
    last_attempt = result["attempts"][-1]
    assert not any(err.get("stage") == "sql_guardrail" for err in last_attempt.get("validation_errors", []))


def test_pipeline_fail_fast_on_guardrail_failure():
    unsafe_sql = "DROP TABLE users;"
    fake_provider = TrackingFakeProvider(
        responses=[unsafe_sql, "SELECT 1;", "SELECT 2;"]  # Subsequent responses should never be used
    )
    
    pipeline = get_mocked_pipeline(llm_provider=fake_provider)
    
    result = pipeline.run_pipeline(natural_query="drop users")
    
    # Assert pipeline fails
    assert result["success"] is False
    
    # Assert fail-fast: only 1 attempt and 1 provider call made
    assert len(result["attempts"]) == 1
    assert fake_provider.call_count == 1
    
    # Assert generated_sql is empty due to sanitization
    assert result["generated_sql"] == ""
    
    # Assert diagnostic information
    first_attempt = result["attempts"][0]
    assert first_attempt["sql"] == unsafe_sql
    assert first_attempt["valid"] is False
    assert any(err.get("stage") == "sql_guardrail" for err in first_attempt.get("validation_errors", []))
