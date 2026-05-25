import pytest
from unittest.mock import MagicMock

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
    assert fake_provider.requests_received[0].purpose == "writer"
    assert fake_provider.requests_received[1].purpose == "corrector"


def test_legacy_nvidia_path_preserved():
    mock_nvidia_client = MagicMock()
    mock_nvidia_client.generate_sql.return_value = "SELECT * FROM customers"
    
    pipeline = get_mocked_pipeline(nvidia_client=mock_nvidia_client, llm_provider=None)
    
    result = pipeline.run_pipeline(natural_query="test query")
    
    assert result["success"] is True
    assert result["generated_sql"] == "SELECT\n  *\nFROM customers"
    mock_nvidia_client.generate_sql.assert_called_once()
