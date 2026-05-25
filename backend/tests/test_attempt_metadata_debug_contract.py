from unittest.mock import MagicMock, patch

from app.sql_pipeline import SQLGenerationPipeline


def get_saved_trace(trace_store):
    trace_store.save.assert_called_once()
    return trace_store.save.call_args[0][0]


def trace_get(trace, field, default=None):
    if isinstance(trace, dict):
        return trace.get(field, default)
    return getattr(trace, field, default)


# 1. Success attempt metadata is complete and consistent
@patch("app.sql_pipeline.PromptTemplateManager.get_writer_prompt", return_value="dummy prompt")
def test_success_attempt_metadata_is_complete_and_consistent(mock_prompt):
    mock_llm_provider = MagicMock()
    mock_response = MagicMock()
    mock_response.sql = "SELECT id FROM users"
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
            natural_query="list user ids",
            max_attempts=1,
        )

    assert result["success"] is True
    assert len(result["attempts"]) == 1

    attempt = result["attempts"][0]

    assert attempt["attempt"] == 1
    assert attempt["action"] == "generate"
    assert attempt["valid"] is True
    assert attempt["error"] is None
    assert attempt["sql"] == result["generated_sql"]
    assert attempt.get("validation_errors", []) == []

    # Trace attempts must exactly match result attempts
    trace = get_saved_trace(trace_store)
    assert trace_get(trace, "attempts") == result["attempts"]


# 2. LLM exception attempt metadata is complete and consistent
@patch("app.sql_pipeline.PromptTemplateManager.get_writer_prompt", return_value="dummy prompt")
def test_llm_exception_attempt_metadata_is_complete_and_consistent(mock_prompt):
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

    attempt = result["attempts"][0]

    assert attempt["attempt"] == 1
    assert attempt["action"] == "generate"
    assert attempt["sql"] == ""
    assert attempt["valid"] is False
    assert attempt["error"] is not None
    assert len(attempt["validation_errors"]) == 1

    err = attempt["validation_errors"][0]
    assert err["type"] == "llm_api_error"
    assert err["stage"] == "llm_generation"

    # Trace attempts must exactly match result attempts
    trace = get_saved_trace(trace_store)
    assert trace_get(trace, "attempts") == result["attempts"]


# 3. Guardrail failure attempt metadata preserves rejected SQL
@patch("app.sql_pipeline.PromptTemplateManager.get_writer_prompt", return_value="dummy prompt")
def test_guardrail_failure_attempt_metadata_preserves_rejected_sql(mock_prompt):
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
    assert len(result["attempts"]) == 1

    attempt = result["attempts"][0]

    assert attempt["attempt"] == 1
    assert attempt["action"] == "generate"
    assert attempt["sql"] == "DROP TABLE users;"
    assert attempt["valid"] is False
    assert attempt["error"] is not None

    err = attempt["validation_errors"][0]
    assert err["type"] == "non_select_statement"
    assert err["stage"] == "sql_guardrail"

    # Guardrail policy: Do not expose unsafe/rejected SQL in public field
    assert result["generated_sql"] == ""

    # Trace attempts must exactly match result attempts
    trace = get_saved_trace(trace_store)
    assert trace_get(trace, "attempts") == result["attempts"]


# 4. Semantic failure attempt metadata carries generated SQL and semantic error
@patch("app.sql_pipeline.PromptTemplateManager.get_writer_prompt", return_value="dummy prompt")
def test_semantic_failure_attempt_metadata_carries_generated_sql_and_semantic_error(mock_prompt):
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
    assert len(result["attempts"]) == 1

    attempt = result["attempts"][0]

    assert attempt["attempt"] == 1
    assert attempt["action"] == "generate"
    assert attempt["sql"] == "SELECT invalid_col FROM users"
    assert attempt["valid"] is False
    assert attempt["error"] is not None

    err = attempt["validation_errors"][0]
    assert err["type"] == "missing_column"
    assert err["stage"] == "semantic_validation"

    # Semantic failure is not unsafe; it carries generated SQL in public field
    assert result["generated_sql"] == attempt["sql"]

    # Trace attempts must exactly match result attempts
    trace = get_saved_trace(trace_store)
    assert trace_get(trace, "attempts") == result["attempts"]


# 5. Syntax/parse failure attempt metadata carries generated SQL and parse error
@patch("app.sql_pipeline.PromptTemplateManager.get_writer_prompt", return_value="dummy prompt")
def test_syntax_parse_failure_attempt_metadata_carries_generated_sql_and_parse_error(mock_prompt):
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
    assert len(result["attempts"]) == 1

    attempt = result["attempts"][0]

    assert attempt["attempt"] == 1
    assert attempt["action"] == "generate"
    assert attempt["sql"] == "SELECT * FROM"
    assert attempt["valid"] is False
    assert attempt["error"] is not None

    err = attempt["validation_errors"][0]
    assert err["type"] in {"sql_parse_error", "syntax_error"}
    assert err["stage"] in {"sql_guardrail", "ast_parse"}

    # Trace attempts must exactly match result attempts
    trace = get_saved_trace(trace_store)
    assert trace_get(trace, "attempts") == result["attempts"]


# 6. Retry/corrector attempt numbering and action consistency
@patch("app.sql_pipeline.PromptTemplateManager.get_corrector_prompt", return_value="dummy corrector prompt")
@patch("app.sql_pipeline.PromptTemplateManager.get_writer_prompt", return_value="dummy writer prompt")
def test_retry_corrector_attempt_numbering_and_action_consistency(mock_writer_prompt, mock_corrector_prompt):
    mock_llm_provider = MagicMock()
    
    mock_response_1 = MagicMock()
    mock_response_1.sql = "SELECT invalid_col FROM users"
    
    mock_response_2 = MagicMock()
    mock_response_2.sql = "SELECT id FROM users"
    
    mock_llm_provider.generate_sql.side_effect = [
        mock_response_1,
        mock_response_2,
    ]

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
            max_attempts=2
        )

    assert result["success"] is True
    assert len(result["attempts"]) == 2

    first = result["attempts"][0]
    second = result["attempts"][1]

    # Attempt 1 metadata shape (generate / fail)
    assert first["attempt"] == 1
    assert first["action"] == "generate"
    assert first["sql"] == "SELECT invalid_col FROM users"
    assert first["valid"] is False
    assert first["error"] is not None
    assert first["validation_errors"][0]["type"] == "missing_column"

    # Attempt 2 metadata shape (correct / success)
    assert second["attempt"] == 2
    assert second["action"] == "correct"
    assert second["valid"] is True
    assert second["error"] is None
    assert second["sql"] == result["generated_sql"]
    assert second.get("validation_errors", []) == []

    # Trace attempts must exactly match result attempts
    trace = get_saved_trace(trace_store)
    assert trace_get(trace, "attempts") == result["attempts"]
