from unittest.mock import MagicMock, patch
import pytest

from app.sql_pipeline import SQLGenerationPipeline

# Helper functions for trace extraction to remain decoupled from underlying type (dataclass vs dict)
def get_saved_trace(trace_store):
    trace_store.save.assert_called_once()
    return trace_store.save.call_args[0][0]


def trace_get(trace, field, default=None):
    if isinstance(trace, dict):
        return trace.get(field, default)
    return getattr(trace, field, default)


# 1. Input failure trace consistency
def test_input_failure_trace_consistency():
    trace_store = MagicMock()
    pipeline = SQLGenerationPipeline(trace_store=trace_store)

    result = pipeline.run_pipeline(
        job_id="test",
        natural_query=None,
        excel_file_path=None,
    )

    assert result["success"] is False
    assert result["generated_sql"] == ""
    assert result["attempts"] == []

    trace = get_saved_trace(trace_store)
    assert trace_get(trace, "error_type") == "input_error"
    assert trace_get(trace, "error_message") is not None
    assert trace_get(trace, "sql_valid") is None
    assert trace_get(trace, "generated_sql") is None
    assert trace_get(trace, "last_generated_sql") is None
    assert trace_get(trace, "sql_validation_errors") == []


# 2. LLM exception failure trace consistency
@patch("app.sql_pipeline.PromptTemplateManager.get_writer_prompt", return_value="dummy prompt")
def test_llm_exception_failure_trace_consistency(mock_prompt):
    mock_llm_provider = MagicMock()
    mock_llm_provider.generate_sql.side_effect = Exception("API Failed")

    trace_store = MagicMock()
    pipeline = SQLGenerationPipeline(
        trace_store=trace_store,
        llm_provider=mock_llm_provider,
    )

    with patch("app.sql_pipeline.SchemaPruner.prune_schema") as mock_prune:
        mock_prune.return_value = {"tables": {}}
        result = pipeline.run_pipeline(
            job_id="test",
            natural_query="test query",
            max_attempts=1
        )

    assert result["success"] is False
    assert len(result["attempts"]) == 1
    assert result["attempts"][0]["valid"] is False
    assert result["attempts"][0]["validation_errors"][0]["type"] == "llm_api_error"

    trace = get_saved_trace(trace_store)
    assert trace_get(trace, "error_type") == "sql_generation_failed"
    assert trace_get(trace, "sql_valid") is False
    assert trace_get(trace, "generated_sql") is None
    assert trace_get(trace, "last_generated_sql") is None
    
    val_errors = trace_get(trace, "sql_validation_errors")
    assert len(val_errors) == 1
    assert val_errors[0]["type"] == "llm_api_error"
    
    trace_attempts = trace_get(trace, "attempts")
    assert len(trace_attempts) == 1
    assert trace_attempts[0]["validation_errors"][0]["type"] == "llm_api_error"


# 3. Guardrail failure trace consistency
@patch("app.sql_pipeline.PromptTemplateManager.get_writer_prompt", return_value="dummy prompt")
def test_guardrail_failure_trace_consistency(mock_prompt):
    mock_llm_provider = MagicMock()
    mock_response = MagicMock()
    mock_response.sql = "DROP TABLE users;"
    mock_llm_provider.generate_sql.return_value = mock_response

    trace_store = MagicMock()
    pipeline = SQLGenerationPipeline(
        trace_store=trace_store,
        llm_provider=mock_llm_provider,
    )

    with patch("app.sql_pipeline.SchemaPruner.prune_schema") as mock_prune:
        mock_prune.return_value = {"tables": {}}
        result = pipeline.run_pipeline(
            job_id="test",
            natural_query="test query",
            max_attempts=1
        )

    assert result["success"] is False
    assert result["generated_sql"] == ""
    assert result["attempts"][0]["sql"] == "DROP TABLE users;"
    assert result["attempts"][0]["validation_errors"][0]["stage"] == "sql_guardrail"

    trace = get_saved_trace(trace_store)
    assert trace_get(trace, "error_type") == "sql_generation_failed"
    assert trace_get(trace, "sql_valid") is False
    assert trace_get(trace, "generated_sql") is None
    assert trace_get(trace, "last_generated_sql") == "DROP TABLE users;"
    assert trace_get(trace, "sql_validation_errors")[0]["stage"] == "sql_guardrail"


# 4. Semantic validation failure trace consistency
@patch("app.sql_pipeline.PromptTemplateManager.get_writer_prompt", return_value="dummy prompt")
def test_semantic_validation_failure_trace_consistency(mock_prompt):
    mock_llm_provider = MagicMock()
    mock_response = MagicMock()
    mock_response.sql = "SELECT invalid_col FROM users"
    mock_llm_provider.generate_sql.return_value = mock_response

    trace_store = MagicMock()
    pipeline = SQLGenerationPipeline(
        trace_store=trace_store,
        llm_provider=mock_llm_provider,
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
    assert result["generated_sql"] == "SELECT invalid_col FROM users"
    assert result["attempts"][0]["validation_errors"][0]["type"] == "missing_column"

    trace = get_saved_trace(trace_store)
    assert trace_get(trace, "error_type") == "sql_generation_failed"
    assert trace_get(trace, "sql_valid") is False
    assert trace_get(trace, "generated_sql") is None
    assert trace_get(trace, "last_generated_sql") == "SELECT invalid_col FROM users"
    
    val_errors = trace_get(trace, "sql_validation_errors")
    assert len(val_errors) == 1
    assert val_errors[0]["type"] == "missing_column"
    assert val_errors[0]["stage"] == "semantic_validation"


# 5. Syntax/parse failure trace consistency
@patch("app.sql_pipeline.PromptTemplateManager.get_writer_prompt", return_value="dummy prompt")
def test_syntax_parse_failure_trace_consistency(mock_prompt):
    mock_llm_provider = MagicMock()
    mock_response = MagicMock()
    mock_response.sql = "SELECT * FROM"
    mock_llm_provider.generate_sql.return_value = mock_response

    trace_store = MagicMock()
    pipeline = SQLGenerationPipeline(
        trace_store=trace_store,
        llm_provider=mock_llm_provider,
    )

    with patch("app.sql_pipeline.SchemaPruner.prune_schema") as mock_prune:
        mock_prune.return_value = {"tables": {"users": ["id"]}}
        result = pipeline.run_pipeline(
            job_id="test",
            natural_query="test query",
            max_attempts=1
        )

    assert result["success"] is False

    trace = get_saved_trace(trace_store)
    assert trace_get(trace, "error_type") == "sql_generation_failed"
    assert trace_get(trace, "sql_valid") is False
    assert trace_get(trace, "generated_sql") is None
    assert trace_get(trace, "last_generated_sql") == "SELECT * FROM"
    
    val_errors = trace_get(trace, "sql_validation_errors")
    assert len(val_errors) == 1
    assert val_errors[0]["type"] in {"sql_parse_error", "syntax_error"}
    assert val_errors[0]["stage"] in {"sql_guardrail", "ast_parse"}
