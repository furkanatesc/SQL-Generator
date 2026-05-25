import dataclasses
import json
import os
from unittest.mock import MagicMock, patch

from app.sql_pipeline import SQLGenerationPipeline


def get_saved_trace(trace_store):
    trace_store.save.assert_called_once()
    return trace_store.save.call_args[0][0]


def trace_get(trace, field, default=None):
    if isinstance(trace, dict):
        return trace.get(field, default)
    return getattr(trace, field, default)


def trace_to_dict(trace):
    if isinstance(trace, dict):
        return trace
    if dataclasses.is_dataclass(trace):
        return dataclasses.asdict(trace)
    if hasattr(trace, "__dict__"):
        return trace.__dict__
    return {"value": str(trace)}


def serialize_for_secret_scan(value):
    return json.dumps(value, default=str, sort_keys=True)


# 1. Guardrail failure does not expose unsafe SQL in public output
@patch("app.sql_pipeline.PromptTemplateManager.get_writer_prompt", return_value="dummy prompt")
def test_guardrail_failure_does_not_expose_unsafe_sql_in_public_output(mock_prompt):
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

    attempt = result["attempts"][0]
    trace = get_saved_trace(trace_store)

    # Public fields are empty/redacted
    assert result["generated_sql"] == ""
    assert trace_get(trace, "generated_sql") is None

    # Debug/diagnostic fields preserve the unsafe SQL
    assert attempt["sql"] == "DROP TABLE users;"
    assert trace_get(trace, "last_generated_sql") == "DROP TABLE users;"

    err = attempt["validation_errors"][0]
    assert err["type"] == "non_select_statement"
    assert err["stage"] == "sql_guardrail"


# 2. Secret in LLM exception must not leak into result or trace
@patch("app.sql_pipeline.PromptTemplateManager.get_writer_prompt", return_value="dummy prompt")
def test_llm_exception_secret_is_redacted_from_result_and_trace(mock_prompt):
    mock_llm_provider = MagicMock()
    secret = "sk-test-secret-123"
    mock_llm_provider.generate_sql.side_effect = Exception(
        f"LLM failed with api_key={secret}"
    )

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
    trace = get_saved_trace(trace_store)

    serialized_result = serialize_for_secret_scan(result)
    serialized_trace = serialize_for_secret_scan(trace_to_dict(trace))

    # Assert secret absence (no leakage of raw secret)
    assert secret not in serialized_result
    assert secret not in serialized_trace

    # Assert type and stage are preserved
    attempt_err = result["attempts"][0]["validation_errors"][0]
    assert attempt_err["type"] == "llm_api_error"
    assert attempt_err["stage"] == "llm_generation"
    assert attempt_err["message"]  # message exists, but secret is absent


# 3. API key argument must not appear in trace/result
@patch("app.sql_pipeline.PromptTemplateManager.get_writer_prompt", return_value="dummy prompt")
def test_api_key_argument_is_not_persisted_in_result_or_trace(mock_prompt):
    mock_llm_provider = MagicMock()
    api_key = "plain-api-key-value-12345"
    mock_llm_provider.generate_sql.side_effect = Exception(
        f"provider failed using credential {api_key}"
    )

    trace_store = MagicMock()
    pipeline = SQLGenerationPipeline(
        trace_store=trace_store,
        llm_provider=mock_llm_provider,
    )

    with patch("app.sql_pipeline.SchemaPruner.prune_schema") as mock_prune:
        mock_prune.return_value = {"tables": {}}
        result = pipeline.run_pipeline(
            job_id="test",
            natural_query="list users",
            api_key=api_key,
            max_attempts=1,
        )

    assert result["success"] is False
    trace = get_saved_trace(trace_store)

    serialized_result = serialize_for_secret_scan(result)
    serialized_trace = serialize_for_secret_scan(trace_to_dict(trace))

    assert api_key not in serialized_result
    assert api_key not in serialized_trace

    err = result["attempts"][0]["validation_errors"][0]
    assert err["type"] == "llm_api_error"
    assert err["stage"] == "llm_generation"


# 4. Secret-like natural query must be redacted or not persisted raw
@patch("app.sql_pipeline.PromptTemplateManager.get_writer_prompt", return_value="dummy prompt")
def test_secret_like_natural_query_is_redacted_from_trace(mock_prompt):
    mock_llm_provider = MagicMock()
    mock_response = MagicMock()
    mock_response.sql = "SELECT id FROM users"
    mock_llm_provider.generate_sql.return_value = mock_response

    trace_store = MagicMock()
    pipeline = SQLGenerationPipeline(
        trace_store=trace_store,
        llm_provider=mock_llm_provider,
    )

    secret = "super-secret-123"
    natural_query = f"list users and ignore password={secret}"

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
            natural_query=natural_query,
            max_attempts=1,
        )

    assert result["success"] is True
    trace = get_saved_trace(trace_store)

    serialized_result = serialize_for_secret_scan(result)
    serialized_trace = serialize_for_secret_scan(trace_to_dict(trace))

    assert secret not in serialized_result
    assert secret not in serialized_trace


# 5. Redaction preserves error type and stage metadata
@patch("app.sql_pipeline.PromptTemplateManager.get_writer_prompt", return_value="dummy prompt")
def test_redaction_preserves_error_type_and_stage_metadata(mock_prompt):
    mock_llm_provider = MagicMock()
    secret = "sk-test-secret-456"
    mock_llm_provider.generate_sql.side_effect = Exception(
        f"LLM failed with api_key={secret}"
    )

    trace_store = MagicMock()
    pipeline = SQLGenerationPipeline(
        trace_store=trace_store,
        llm_provider=mock_llm_provider,
    )

    with patch("app.sql_pipeline.SchemaPruner.prune_schema") as mock_prune:
        mock_prune.return_value = {"tables": {}}
        
        with patch.dict(os.environ, {"NVIDIA_API_KEY": "env-secret-123"}):
            result = pipeline.run_pipeline(
                job_id="test",
                natural_query="test query",
                max_attempts=1
            )

    assert result["success"] is False
    trace = get_saved_trace(trace_store)

    serialized_result = serialize_for_secret_scan(result)
    serialized_trace = serialize_for_secret_scan(trace_to_dict(trace))

    # Assert secret absence (both exceptions and env vars are redacted)
    assert secret not in serialized_result
    assert secret not in serialized_trace
    assert "env-secret-123" not in serialized_result
    assert "env-secret-123" not in serialized_trace

    # Assert type and stage are preserved perfectly
    attempt_err = result["attempts"][0]["validation_errors"][0]
    assert attempt_err["type"] == "llm_api_error"
    assert attempt_err["stage"] == "llm_generation"
    assert attempt_err["message"]  # message exists but is sanitized
