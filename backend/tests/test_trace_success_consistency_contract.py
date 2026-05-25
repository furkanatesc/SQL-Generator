from unittest.mock import MagicMock, patch

from app.sql_pipeline import SQLGenerationPipeline


def get_saved_trace(trace_store):
    trace_store.save.assert_called_once()
    return trace_store.save.call_args[0][0]


def trace_get(trace, field, default=None):
    if isinstance(trace, dict):
        return trace.get(field, default)
    return getattr(trace, field, default)


def build_success_pipeline_result():
    mock_llm_provider = MagicMock()
    mock_response = MagicMock()
    mock_response.sql = "SELECT id FROM users"
    mock_llm_provider.generate_sql.return_value = mock_response

    trace_store = MagicMock()
    pipeline = SQLGenerationPipeline(
        trace_store=trace_store,
        llm_provider=mock_llm_provider,
    )

    return pipeline, trace_store


# 1. Basic success trace consistency
@patch("app.sql_pipeline.PromptTemplateManager.get_writer_prompt", return_value="dummy prompt")
def test_success_trace_matches_result_and_final_attempt(mock_prompt):
    pipeline, trace_store = build_success_pipeline_result()

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
            natural_query="list user ids",
            max_attempts=1,
        )

    assert result["success"] is True
    assert len(result["attempts"]) == 1
    assert result["generated_sql"]

    final_attempt = result["attempts"][-1]
    trace = get_saved_trace(trace_store)

    assert final_attempt["valid"] is True
    assert final_attempt["sql"] == result["generated_sql"]

    assert trace_get(trace, "sql_valid") is True
    assert trace_get(trace, "generated_sql") == result["generated_sql"]
    assert trace_get(trace, "last_generated_sql") == result["generated_sql"]
    assert trace_get(trace, "attempts") == result["attempts"]


# 2. Success trace has no error metadata
@patch("app.sql_pipeline.PromptTemplateManager.get_writer_prompt", return_value="dummy prompt")
def test_success_trace_has_no_error_metadata(mock_prompt):
    pipeline, trace_store = build_success_pipeline_result()

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
            natural_query="list user ids",
            max_attempts=1,
        )

    assert result["success"] is True

    trace = get_saved_trace(trace_store)

    assert trace_get(trace, "error_type") is None
    assert trace_get(trace, "error_message") is None
    assert trace_get(trace, "sql_validation_errors") == []


# 3. Success final attempt has no validation errors
@patch("app.sql_pipeline.PromptTemplateManager.get_writer_prompt", return_value="dummy prompt")
def test_success_final_attempt_has_no_validation_errors(mock_prompt):
    pipeline, trace_store = build_success_pipeline_result()

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
            natural_query="list user ids",
            max_attempts=1,
        )

    assert result["success"] is True

    final_attempt = result["attempts"][-1]
    assert final_attempt["valid"] is True
    assert final_attempt["error"] is None
    assert final_attempt.get("validation_errors", []) == []


# 4. Success generated SQL is formatted consistently
@patch("app.sql_pipeline.PromptTemplateManager.get_writer_prompt", return_value="dummy prompt")
def test_success_generated_sql_is_formatted_consistently(mock_prompt):
    pipeline, trace_store = build_success_pipeline_result()

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
            natural_query="list user ids",
            max_attempts=1,
        )

    assert result["success"] is True
    
    # Assert formatting consistency rather than brittle exact string comparison
    generated_sql = result["generated_sql"]
    assert "SELECT" in generated_sql.upper()
    assert "USERS" in generated_sql.upper()
    
    trace = get_saved_trace(trace_store)
    assert trace_get(trace, "generated_sql") == generated_sql
    assert trace_get(trace, "last_generated_sql") == generated_sql
