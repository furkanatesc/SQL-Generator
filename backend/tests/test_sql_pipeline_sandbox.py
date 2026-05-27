import pytest
from unittest.mock import patch, MagicMock
from app.sql_pipeline import SQLGenerationPipeline
from app.llm.provider import LLMProvider, SQLGenerationResponse

class TrackingFakeProvider(LLMProvider):
    def __init__(self, response):
        self.response = response

    def generate_sql(self, request) -> SQLGenerationResponse:
        return SQLGenerationResponse(sql=self.response, provider_name="fake")

def get_mocked_pipeline(llm_provider):
    mock_schema_manager = MagicMock()
    return SQLGenerationPipeline(
        schema_manager=mock_schema_manager,
        llm_provider=llm_provider
    )

def test_pipeline_rejection_multiple_statements_guardrail():
    """
    Verifies that a multiple statement SQL injection attack (e.g. SELECT; DROP)
    is caught early and blocked by the standard SQLGuardrailValidator,
    reporting the validation stage as 'sql_guardrail' and keeping public generated_sql empty.
    """
    fake_provider = TrackingFakeProvider(response="SELECT * FROM users; DROP TABLE users;")
    pipeline = get_mocked_pipeline(fake_provider)
    
    with patch.object(pipeline.schema_pruner, 'prune_schema', return_value={"tables": {"users": {}}}):
        result = pipeline.run_pipeline(natural_query="get users and drop table", max_attempts=1)
        
    assert result["success"] is False
    assert result["generated_sql"] == ""  # Unsafe SQL must not be returned in public generated_sql
    assert len(result["attempts"]) == 1
    
    attempt = result["attempts"][0]
    assert attempt["valid"] is False
    
    val_errors = attempt["validation_errors"]
    assert any(err["stage"] == "sql_guardrail" for err in val_errors)
    assert any(err["type"] == "multiple_statements" for err in val_errors)

def test_pipeline_rejection_admin_pragma_sandbox():
    """
    Verifies that a select-based admin query (e.g. SELECT * FROM pragma;)
    which passes standard guardrails is caught and blocked by our new
    SqlSafetyValidator sandbox layer, reporting the stage as 'sql_sandbox_safety'
    and keeping public generated_sql empty.
    """
    fake_provider = TrackingFakeProvider(response="SELECT * FROM pragma;")
    pipeline = get_mocked_pipeline(fake_provider)
    
    with patch.object(pipeline.schema_pruner, 'prune_schema', return_value={"tables": {"users": {}}}):
        result = pipeline.run_pipeline(natural_query="get db version", max_attempts=1)
        
    assert result["success"] is False
    assert result["generated_sql"] == ""  # Unsafe SQL must not be returned in public generated_sql
    assert len(result["attempts"]) == 1
    
    attempt = result["attempts"][0]
    assert attempt["valid"] is False
    
    val_errors = attempt["validation_errors"]
    assert len(val_errors) == 1
    err = val_errors[0]
    assert err["type"] == "unsafe_sql"
    assert err["stage"] == "sql_sandbox_safety"
    assert "PRAGMA" in err["message"]
