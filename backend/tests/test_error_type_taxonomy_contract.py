from unittest.mock import MagicMock, patch

from app.sql_pipeline import SQLGenerationPipeline
from app.sql_guardrail import SQLGuardrailValidator

ALLOWED_ERROR_TYPES = {
    "input_error",
    "excel_parse_error",
    "schema_pruning_error",
    "schema_pruning_exception",
    "sql_generation_failed",
    "llm_api_error",
    "sql_parse_error",
    "syntax_error",
    "semantic_validation",
    "validation_error",
    "missing_table",
    "missing_column",
    "unsupported_dialect",
    "empty_sql",
    "multiple_statements",
    "non_select_statement",
    "unsafe_sql"
}


def test_pipeline_input_error_uses_stable_error_type():
    trace_store = MagicMock()
    pipeline = SQLGenerationPipeline(trace_store=trace_store)
    
    result = pipeline.run_pipeline(
        job_id="test",
        natural_query=None,
        excel_file_path=None
    )
    
    assert result["success"] is False
    
    trace_store.save.assert_called_once()
    trace = trace_store.save.call_args[0][0]
    err_type = getattr(trace, "error_type", None)
    if err_type is None and isinstance(trace, dict):
        err_type = trace.get("error_type")
        
    assert err_type == "input_error"
    assert err_type in ALLOWED_ERROR_TYPES


@patch("app.sql_pipeline.PromptTemplateManager.get_writer_prompt", return_value="dummy prompt")
def test_pipeline_llm_exception_uses_stable_validation_error_type(mock_prompt):
    mock_llm_provider = MagicMock()
    mock_llm_provider.generate_sql.side_effect = Exception("API Failed")
    
    trace_store = MagicMock()
    pipeline = SQLGenerationPipeline(
        trace_store=trace_store,
        llm_provider=mock_llm_provider
    )
    
    with patch("app.sql_pipeline.SchemaPruner.prune_schema") as mock_prune:
        mock_prune.return_value = {"tables": {}}
        result = pipeline.run_pipeline(
            job_id="test",
            natural_query="test query",
            max_attempts=1
        )
        
    assert result["success"] is False
    
    attempts = result["attempts"]
    assert len(attempts) > 0
    err = attempts[0]["validation_errors"][0]
    
    assert err["type"] == "llm_api_error"
    assert err["stage"] == "llm_generation"
    assert err["type"] in ALLOWED_ERROR_TYPES


def test_guardrail_non_select_uses_stable_error_type():
    errors = SQLGuardrailValidator.validate("DROP TABLE users;")
    assert len(errors) > 0
    err = errors[0]
    assert err["type"] == "non_select_statement"
    assert err["stage"] == "sql_guardrail"
    assert err["type"] in ALLOWED_ERROR_TYPES


def test_guardrail_multiple_statements_uses_stable_error_type():
    errors = SQLGuardrailValidator.validate("SELECT 1; SELECT 2;")
    assert len(errors) > 0
    err = errors[0]
    assert err["type"] == "multiple_statements"
    assert err["stage"] == "sql_guardrail"
    assert err["type"] in ALLOWED_ERROR_TYPES


def test_guardrail_dangerous_function_uses_stable_error_type():
    errors = SQLGuardrailValidator.validate("SELECT pg_sleep(10)")
    assert len(errors) > 0
    err = errors[0]
    assert err["type"] == "unsafe_sql"
    assert err["stage"] == "sql_guardrail"
    assert err["type"] in ALLOWED_ERROR_TYPES


@patch("app.sql_pipeline.PromptTemplateManager.get_writer_prompt", return_value="dummy prompt")
def test_pipeline_semantic_failure_uses_stable_validation_error_type(mock_prompt):
    mock_llm_provider = MagicMock()
    mock_response = MagicMock()
    mock_response.sql = "SELECT invalid_col FROM users"
    mock_llm_provider.generate_sql.return_value = mock_response
    
    trace_store = MagicMock()
    pipeline = SQLGenerationPipeline(
        trace_store=trace_store,
        llm_provider=mock_llm_provider
    )
    
    with patch("app.sql_pipeline.SchemaPruner.prune_schema") as mock_prune:
        mock_prune.return_value = {
            "tables": {
                "users": {
                    "columns": [{"name": "id"}]
                }
            }
        }
        
        result = pipeline.run_pipeline(
            job_id="test",
            natural_query="test query",
            max_attempts=1
        )
            
    assert result["success"] is False
    err = result["attempts"][0]["validation_errors"][0]
    assert err["type"] == "missing_column"
    assert err["stage"] == "semantic_validation"
    assert err["type"] in ALLOWED_ERROR_TYPES


@patch("app.sql_pipeline.PromptTemplateManager.get_writer_prompt", return_value="dummy prompt")
def test_all_pipeline_validation_error_types_are_known_taxonomy_values(mock_prompt):
    mock_llm_provider = MagicMock()
    mock_response = MagicMock()
    mock_response.sql = "SELECT * FROM"  # syntax error
    mock_llm_provider.generate_sql.return_value = mock_response
    
    trace_store = MagicMock()
    pipeline = SQLGenerationPipeline(
        trace_store=trace_store,
        llm_provider=mock_llm_provider
    )
    
    with patch("app.sql_pipeline.SchemaPruner.prune_schema") as mock_prune:
        mock_prune.return_value = {"tables": {"users": ["id"]}}
        result = pipeline.run_pipeline(
            job_id="test",
            natural_query="test query",
            max_attempts=1
        )
        
    assert result["success"] is False
    
    for attempt in result["attempts"]:
        for err in attempt.get("validation_errors", []):
            assert err["type"] in ALLOWED_ERROR_TYPES
            assert "stage" in err
            
    trace_store.save.assert_called_once()
    trace = trace_store.save.call_args[0][0]
    trace_val_errors = getattr(trace, "sql_validation_errors", None)
    if trace_val_errors is None and isinstance(trace, dict):
        trace_val_errors = trace.get("sql_validation_errors", [])
        
    for err in trace_val_errors or []:
        assert err["type"] in ALLOWED_ERROR_TYPES
        assert "stage" in err
