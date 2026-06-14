import pytest
import hashlib
import socket
from app.sql_generation.sql_generation_provider_contract import (
    SQLGenerationProviderRequest,
    SQLGenerationProviderResponse,
    SQLGenerationProviderResult,
)
from app.prompting.structured_output_contract import (
    SQLStructuredOutputConfig,
    SQLStructuredOutputResult,
    SQLStructuredOutputContractError,
)
from app.prompting.structured_output_parser import SQLStructuredOutputParser


def make_mock_provider_result(
    raw_text: str,
    finish_reason: str = "stop",
    provider_id: str = "openai",
    model_id: str = "gpt-4",
    prompt: str = "some prompt text",
) -> SQLGenerationProviderResult:
    prompt_sha = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    output_sha = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    
    req = SQLGenerationProviderRequest(
        version="sql_generation_provider_v1",
        input_version="input_v1",
        query_id="query-123",
        prompt=prompt,
        prompt_sha256=prompt_sha,
        target_dialect="sqlite",
        constraints=(),
        provider_id=provider_id,
        model_id=model_id,
        temperature=0.0,
        max_output_tokens=None,
        metadata={},
    )
    res = SQLGenerationProviderResponse(
        version="sql_generation_provider_v1",
        provider_id=provider_id,
        model_id=model_id,
        raw_text=raw_text,
        finish_reason=finish_reason,
        prompt_sha256=prompt_sha,
        output_sha256=output_sha,
        latency_ms=100,
        token_usage=None,
        metadata={},
    )
    return SQLGenerationProviderResult(
        version="sql_generation_provider_v1",
        request=req,
        response=res,
        generated_sql_text=raw_text,
        prompt_sha256=prompt_sha,
        output_sha256=output_sha,
    )


def test_parser_rejects_none_provider_result():
    parser = SQLStructuredOutputParser()
    config = SQLStructuredOutputConfig()
    with pytest.raises(SQLStructuredOutputContractError) as exc_info:
        parser.parse(None, config)  # type: ignore
    assert "provider_result cannot be None" in str(exc_info.value)


def test_parser_rejects_none_config():
    parser = SQLStructuredOutputParser()
    result = make_mock_provider_result("SELECT 1")
    with pytest.raises(SQLStructuredOutputContractError) as exc_info:
        parser.parse(result, None)  # type: ignore
    assert "config cannot be None" in str(exc_info.value)


def test_parser_rejects_empty_raw_text():
    from unittest.mock import Mock
    parser = SQLStructuredOutputParser()
    config = SQLStructuredOutputConfig()
    
    result = Mock(spec=SQLGenerationProviderResult)
    result.response = Mock()
    result.response.raw_text = ""
    result.response.finish_reason = "stop"
    
    with pytest.raises(SQLStructuredOutputContractError) as exc_info:
        parser.parse(result, config)
    assert "raw_text cannot be empty" in str(exc_info.value)


def test_parser_rejects_whitespace_raw_text():
    from unittest.mock import Mock
    parser = SQLStructuredOutputParser()
    config = SQLStructuredOutputConfig()
    
    result = Mock(spec=SQLGenerationProviderResult)
    result.response = Mock()
    result.response.raw_text = "   \n   \t  "
    result.response.finish_reason = "stop"
    
    with pytest.raises(SQLStructuredOutputContractError) as exc_info:
        parser.parse(result, config)
    assert "raw_text cannot be empty" in str(exc_info.value)


def test_parser_rejects_markdown_code_fence():
    parser = SQLStructuredOutputParser()
    config = SQLStructuredOutputConfig()
    
    result_with_fence_sql = make_mock_provider_result("```sql\nSELECT id, name FROM users\n```")
    with pytest.raises(SQLStructuredOutputContractError) as exc_info:
        parser.parse(result_with_fence_sql, config)
    assert "Markdown code fences" in str(exc_info.value)

    result_with_fence_plain = make_mock_provider_result("```\nSELECT id, name FROM users\n```")
    with pytest.raises(SQLStructuredOutputContractError) as exc_info:
        parser.parse(result_with_fence_plain, config)
    assert "Markdown code fences" in str(exc_info.value)


def test_parser_rejects_explanation_text():
    parser = SQLStructuredOutputParser()
    config = SQLStructuredOutputConfig()

    # Heuristic: First clean line must start with valid SQL keyword
    result_with_intro = make_mock_provider_result("Sure! Here is the SQL query:\nSELECT id, name FROM users")
    with pytest.raises(SQLStructuredOutputContractError) as exc_info:
        parser.parse(result_with_intro, config)
    assert "Prose/explanation detected" in str(exc_info.value)

    # Heuristic: Line ending with period and containing no SQL operators/symbols
    result_with_outro = make_mock_provider_result("SELECT id, name FROM users;\nThis query selects all rows.")
    with pytest.raises(SQLStructuredOutputContractError) as exc_info:
        parser.parse(result_with_outro, config)
    assert "Prose/explanation text detected" in str(exc_info.value)


def test_parser_rejects_explanation_text_without_period():
    parser = SQLStructuredOutputParser()
    config = SQLStructuredOutputConfig()

    # Outro prose without period, with semicolon
    result_with_semicolon = make_mock_provider_result(
        "SELECT id, name FROM users;\nThis query returns active users"
    )
    with pytest.raises(SQLStructuredOutputContractError) as exc_info:
        parser.parse(result_with_semicolon, config)
    assert "prose/explanation" in str(exc_info.value).lower() or "after sql statement" in str(exc_info.value).lower()

    # Outro prose without period, without semicolon
    result_no_semicolon = make_mock_provider_result(
        "SELECT id, name FROM users\nThis query returns active users"
    )
    with pytest.raises(SQLStructuredOutputContractError) as exc_info:
        parser.parse(result_no_semicolon, config)
    assert "prose/explanation" in str(exc_info.value).lower()


def test_parser_rejects_outro_prose_after_sql():
    parser = SQLStructuredOutputParser()
    config = SQLStructuredOutputConfig()

    result = make_mock_provider_result(
        "SELECT id, name FROM users;\nHere is how it works under the hood."
    )
    with pytest.raises(SQLStructuredOutputContractError) as exc_info:
        parser.parse(result, config)
    assert "prose/explanation" in str(exc_info.value).lower() or "after sql statement" in str(exc_info.value).lower()


def test_parser_rejects_explanation_label_after_sql():
    parser = SQLStructuredOutputParser()
    config = SQLStructuredOutputConfig()

    # Label with semicolon
    result_label = make_mock_provider_result(
        "SELECT id, name FROM users;\nNote: This is an important warning."
    )
    with pytest.raises(SQLStructuredOutputContractError) as exc_info:
        parser.parse(result_label, config)
    assert "prose/explanation" in str(exc_info.value).lower() or "after sql statement" in str(exc_info.value).lower()

    # Standalone label line
    result_standalone = make_mock_provider_result(
        "SELECT id, name FROM users\nExplanation"
    )
    with pytest.raises(SQLStructuredOutputContractError) as exc_info:
        parser.parse(result_standalone, config)
    assert "label" in str(exc_info.value).lower() or "explanation" in str(exc_info.value).lower()


def test_parser_rejects_length_finish_reason():
    parser = SQLStructuredOutputParser()
    config = SQLStructuredOutputConfig()
    result = make_mock_provider_result("SELECT id, name FROM users", finish_reason="length")
    with pytest.raises(SQLStructuredOutputContractError) as exc_info:
        parser.parse(result, config)
    assert "Provider generation failed with finish_reason: 'length'" in str(exc_info.value)


def test_parser_rejects_unknown_finish_reason():
    parser = SQLStructuredOutputParser()
    config = SQLStructuredOutputConfig()
    result = make_mock_provider_result("SELECT id, name FROM users", finish_reason="weird_provider_state")
    with pytest.raises(SQLStructuredOutputContractError) as exc_info:
        parser.parse(result, config)
    assert "finish_reason: 'weird_provider_state'" in str(exc_info.value)


def test_parser_accepts_stop_finish_reason():
    parser = SQLStructuredOutputParser()
    config = SQLStructuredOutputConfig()
    result = make_mock_provider_result("SELECT id, name FROM users", finish_reason="stop")
    parsed = parser.parse(result, config)
    assert parsed.finish_reason == "stop"


def test_parser_accepts_stop_sequence_finish_reason():
    parser = SQLStructuredOutputParser()
    config = SQLStructuredOutputConfig()
    result = make_mock_provider_result("SELECT id, name FROM users", finish_reason="stop_sequence")
    parsed = parser.parse(result, config)
    assert parsed.finish_reason == "stop_sequence"


def test_parser_bypasses_clean_sql_checks_when_disabled():
    parser = SQLStructuredOutputParser()
    # disable require_clean_sql
    config = SQLStructuredOutputConfig(require_clean_sql=False)
    
    # Text contains markdown fences, intro/outro prose, and labels - but should pass!
    raw_text = "```sql\nHere is query:\nSELECT id, name FROM users;\nNote: returns users\n```"
    result = make_mock_provider_result(raw_text, finish_reason="stop")
    
    parsed = parser.parse(result, config)
    assert parsed.sql_text == raw_text
    assert parsed.warnings == ()


def test_parser_accepts_plain_sql_only_output():
    parser = SQLStructuredOutputParser()
    config = SQLStructuredOutputConfig()
    sql = "SELECT id, name FROM users WHERE age > 18 ORDER BY name ASC LIMIT 10"
    result = make_mock_provider_result(sql)
    
    parsed = parser.parse(result, config)
    assert isinstance(parsed, SQLStructuredOutputResult)
    assert parsed.sql_text == sql
    assert parsed.warnings == ()


def test_parser_accepts_sql_with_comments():
    parser = SQLStructuredOutputParser()
    config = SQLStructuredOutputConfig()
    sql = "-- This is a query to select users\nSELECT id, name FROM users /* inline comment */"
    result = make_mock_provider_result(sql)
    
    parsed = parser.parse(result, config)
    assert parsed.sql_text == sql


def test_parser_computes_sql_sha256():
    parser = SQLStructuredOutputParser()
    config = SQLStructuredOutputConfig()
    sql = "SELECT id, name FROM users"
    result = make_mock_provider_result(sql)
    
    parsed = parser.parse(result, config)
    expected_sha = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    assert parsed.sql_sha256 == expected_sha


def test_parser_computes_sql_char_count():
    parser = SQLStructuredOutputParser()
    config = SQLStructuredOutputConfig()
    sql = "SELECT id, name FROM users"
    result = make_mock_provider_result(sql)
    
    parsed = parser.parse(result, config)
    assert parsed.sql_char_count == len(sql)


def test_parser_computes_raw_text_sha256():
    parser = SQLStructuredOutputParser()
    config = SQLStructuredOutputConfig()
    sql = "SELECT id, name FROM users"
    result = make_mock_provider_result(sql)
    
    parsed = parser.parse(result, config)
    expected_sha = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    assert parsed.raw_text_sha256 == expected_sha


def test_parser_preserves_provider_metadata():
    parser = SQLStructuredOutputParser()
    config = SQLStructuredOutputConfig()
    result = make_mock_provider_result(
        "SELECT id, name FROM users",
        provider_id="anthropic",
        model_id="claude-3-opus",
        finish_reason="stop_sequence"
    )
    
    parsed = parser.parse(result, config)
    assert parsed.provider_name == "anthropic"
    assert parsed.provider_model == "claude-3-opus"
    assert parsed.finish_reason == "stop_sequence"


def test_parser_is_deterministic_for_same_input():
    parser = SQLStructuredOutputParser()
    config = SQLStructuredOutputConfig()
    result1 = make_mock_provider_result("SELECT id, name FROM users")
    result2 = make_mock_provider_result("SELECT id, name FROM users")
    
    parsed1 = parser.parse(result1, config)
    parsed2 = parser.parse(result2, config)
    
    assert parsed1 == parsed2


def test_parser_does_not_call_provider_or_network(monkeypatch):
    def block_socket(*args, **kwargs):
        raise RuntimeError("Network calls are blocked during tests.")
    monkeypatch.setattr(socket, "socket", block_socket)
    
    parser = SQLStructuredOutputParser()
    config = SQLStructuredOutputConfig()
    result = make_mock_provider_result("SELECT id, name FROM users")
    
    parsed = parser.parse(result, config)
    assert parsed.sql_text == "SELECT id, name FROM users"
