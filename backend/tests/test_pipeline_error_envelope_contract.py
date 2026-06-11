import pytest
from unittest.mock import patch, MagicMock
from app.sql_pipeline import SQLGenerationPipeline
from app.llm.provider import LLMProvider, SQLGenerationResponse

class TrackingFakeProvider(LLMProvider):
    def __init__(self, responses=None, exception=None):
        self.responses = responses or []
        self.exception = exception
        self.call_count = 0

    def generate_sql(self, request) -> SQLGenerationResponse:
        if self.exception:
            raise self.exception
        response = self.responses[self.call_count % len(self.responses)]
        self.call_count += 1
        return SQLGenerationResponse(sql=response, provider_name="fake")

def get_mocked_pipeline(llm_provider=None):
    mock_schema_manager = MagicMock()
    pipeline = SQLGenerationPipeline(
        schema_manager=mock_schema_manager,
        llm_provider=llm_provider
    )
    return pipeline

def assert_error_envelope(result: dict):
    assert result["success"] is False
    assert isinstance(result.get("error"), str) and len(result["error"]) > 0
    assert "generated_sql" in result
    assert isinstance(result.get("attempts"), list)
    assert "aqr" in result
    assert isinstance(result.get("pruned_schema_tables"), list)

def assert_attempt_shape(attempt: dict):
    assert "attempt" in attempt
    assert "action" in attempt
    assert "sql" in attempt
    assert "valid" in attempt
    assert "error" in attempt
    assert isinstance(attempt.get("validation_errors", []), list)

def assert_validation_error_shape(err: dict):
    assert "type" in err
    assert "stage" in err
    assert "message" in err

def test_pipeline_input_error_envelope_shape():
    pipeline = get_mocked_pipeline()
    
    # Empty input triggers input error
    result = pipeline.run_pipeline(natural_query=None, excel_file_path=None)
    
    assert_error_envelope(result)
    assert result["attempts"] == []
    assert result["aqr"] is None

def test_pipeline_guardrail_failure_error_envelope_shape():
    fake_provider = TrackingFakeProvider(responses=["DROP TABLE users;"])
    pipeline = get_mocked_pipeline(llm_provider=fake_provider)
    
    with patch.object(pipeline.schema_pruner, 'prune_schema', return_value={"tables": {"users": {"columns": [{"name": "id", "type": "int", "primary_key": True}]}}}):
        result = pipeline.run_pipeline(natural_query="drop users", max_attempts=1)
    
    assert_error_envelope(result)
    assert result["generated_sql"] == ""
    assert len(result["attempts"]) == 1
    
    attempt = result["attempts"][0]
    assert_attempt_shape(attempt)
    assert attempt["sql"] == "DROP TABLE users;"
    
    val_errors = attempt["validation_errors"]
    assert len(val_errors) > 0
    for err in val_errors:
        assert_validation_error_shape(err)
    
    assert any(err["stage"] == "sql_guardrail" for err in val_errors)

def test_pipeline_non_guardrail_failure_error_envelope_shape():
    fake_provider = TrackingFakeProvider(responses=["SELECT * FROM missing_table"])
    pipeline = get_mocked_pipeline(llm_provider=fake_provider)
    
    with patch.object(pipeline.schema_pruner, 'prune_schema', return_value={"tables": {"valid_table": {"columns": [{"name": "id", "type": "int", "primary_key": True}]}}}):
        # Force semantic failure via SQLValidator
        with patch('app.sql_pipeline.SQLValidator.validate', return_value=(False, "Missing column or table")):
            result = pipeline.run_pipeline(natural_query="select", max_attempts=1)
    
    assert_error_envelope(result)
    assert result["generated_sql"] == "SELECT * FROM missing_table"
    assert len(result["attempts"]) == 1
    
    attempt = result["attempts"][0]
    assert_attempt_shape(attempt)
    assert attempt["sql"] == "SELECT * FROM missing_table"
    
    val_errors = attempt["validation_errors"]
    assert len(val_errors) > 0
    for err in val_errors:
        assert_validation_error_shape(err)
        
    assert any(err["stage"] in ["semantic_validation", "ast_parse"] for err in val_errors)

def test_pipeline_llm_exception_error_envelope_shape():
    fake_provider = TrackingFakeProvider(exception=Exception("LLM Down"))
    pipeline = get_mocked_pipeline(llm_provider=fake_provider)
    
    with patch.object(pipeline.schema_pruner, 'prune_schema', return_value={"tables": {"users": {"columns": [{"name": "id", "type": "int", "primary_key": True}]}}}):
        result = pipeline.run_pipeline(natural_query="select", max_attempts=1)
    
    assert_error_envelope(result)
    assert len(result["attempts"]) == 1
    
    attempt = result["attempts"][0]
    assert_attempt_shape(attempt)
    
    val_errors = attempt["validation_errors"]
    assert len(val_errors) > 0
    for err in val_errors:
        assert_validation_error_shape(err)
        
    assert any(err["stage"] == "llm_generation" for err in val_errors)
