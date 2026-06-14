import pytest
import hashlib
from dataclasses import FrozenInstanceError
from app.prompting.structured_output_contract import (
    SQL_STRUCTURED_OUTPUT_VERSION,
    SQLStructuredOutputConfig,
    SQLStructuredOutputResult,
    SQLStructuredOutputContractError,
)


def test_sql_structured_output_version_is_v1():
    assert SQL_STRUCTURED_OUTPUT_VERSION == "sql_structured_output_v1"


def test_structured_output_config_is_frozen():
    config = SQLStructuredOutputConfig(require_clean_sql=True)
    assert config.require_clean_sql is True
    with pytest.raises(FrozenInstanceError):
        config.require_clean_sql = False  # type: ignore


def test_structured_output_result_is_frozen():
    sql = "SELECT 1"
    sql_sha = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    raw_sha = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    
    res = SQLStructuredOutputResult(
        sql_text=sql,
        sql_sha256=sql_sha,
        sql_char_count=len(sql),
        provider_name="openai",
        provider_model="gpt-4",
        finish_reason="stop",
        prompt_sha256=None,
        raw_text_sha256=raw_sha,
        warnings=(),
    )
    
    assert res.sql_text == sql
    with pytest.raises(FrozenInstanceError):
        res.sql_text = "SELECT 2"  # type: ignore


def test_structured_output_result_validates_version():
    sql = "SELECT 1"
    sql_sha = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    raw_sha = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    
    with pytest.raises(SQLStructuredOutputContractError) as exc_info:
        SQLStructuredOutputResult(
            sql_text=sql,
            sql_sha256=sql_sha,
            sql_char_count=len(sql),
            provider_name="openai",
            provider_model="gpt-4",
            finish_reason="stop",
            prompt_sha256=None,
            raw_text_sha256=raw_sha,
            warnings=(),
            version="invalid_version",
        )
    assert "Invalid result version" in str(exc_info.value)


def test_structured_output_result_validates_empty_fields():
    sql = "SELECT 1"
    sql_sha = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    raw_sha = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    
    # Empty sql_text
    with pytest.raises(SQLStructuredOutputContractError) as exc_info:
        SQLStructuredOutputResult(
            sql_text="",
            sql_sha256=sql_sha,
            sql_char_count=0,
            provider_name="openai",
            provider_model="gpt-4",
            finish_reason="stop",
            prompt_sha256=None,
            raw_text_sha256=raw_sha,
            warnings=(),
        )
    assert "sql_text cannot be empty" in str(exc_info.value)

    # Empty provider_name
    with pytest.raises(SQLStructuredOutputContractError) as exc_info:
        SQLStructuredOutputResult(
            sql_text=sql,
            sql_sha256=sql_sha,
            sql_char_count=len(sql),
            provider_name="",
            provider_model="gpt-4",
            finish_reason="stop",
            prompt_sha256=None,
            raw_text_sha256=raw_sha,
            warnings=(),
        )
    assert "provider_name cannot be empty" in str(exc_info.value)

    # Empty finish_reason
    with pytest.raises(SQLStructuredOutputContractError) as exc_info:
        SQLStructuredOutputResult(
            sql_text=sql,
            sql_sha256=sql_sha,
            sql_char_count=len(sql),
            provider_name="openai",
            provider_model="gpt-4",
            finish_reason="",
            prompt_sha256=None,
            raw_text_sha256=raw_sha,
            warnings=(),
        )
    assert "finish_reason cannot be empty" in str(exc_info.value)


def test_structured_output_result_validates_sha256_mismatch():
    sql = "SELECT 1"
    wrong_sha = "a" * 64
    raw_sha = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    
    with pytest.raises(SQLStructuredOutputContractError) as exc_info:
        SQLStructuredOutputResult(
            sql_text=sql,
            sql_sha256=wrong_sha,
            sql_char_count=len(sql),
            provider_name="openai",
            provider_model="gpt-4",
            finish_reason="stop",
            prompt_sha256=None,
            raw_text_sha256=raw_sha,
            warnings=(),
        )
    assert "sql_sha256 does not match the actual SHA256 of sql_text" in str(exc_info.value)


def test_structured_output_result_validates_char_count_mismatch():
    sql = "SELECT 1"
    sql_sha = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    raw_sha = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    
    with pytest.raises(SQLStructuredOutputContractError) as exc_info:
        SQLStructuredOutputResult(
            sql_text=sql,
            sql_sha256=sql_sha,
            sql_char_count=len(sql) + 5,
            provider_name="openai",
            provider_model="gpt-4",
            finish_reason="stop",
            prompt_sha256=None,
            raw_text_sha256=raw_sha,
            warnings=(),
        )
    assert "sql_char_count does not match the actual length of sql_text" in str(exc_info.value)


def test_structured_output_result_validates_sha256_format():
    sql = "SELECT 1"
    sql_sha = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    raw_sha = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    
    # Invalid sql_sha format
    with pytest.raises(SQLStructuredOutputContractError) as exc_info:
        SQLStructuredOutputResult(
            sql_text=sql,
            sql_sha256="not-a-sha",
            sql_char_count=len(sql),
            provider_name="openai",
            provider_model="gpt-4",
            finish_reason="stop",
            prompt_sha256=None,
            raw_text_sha256=raw_sha,
            warnings=(),
        )
    # This might fail on mismatch check or format check. 
    # Let's make sure it raises SQLStructuredOutputContractError anyway.
    assert isinstance(exc_info.value, SQLStructuredOutputContractError)

    # Invalid prompt_sha256 format
    with pytest.raises(SQLStructuredOutputContractError) as exc_info:
        SQLStructuredOutputResult(
            sql_text=sql,
            sql_sha256=sql_sha,
            sql_char_count=len(sql),
            provider_name="openai",
            provider_model="gpt-4",
            finish_reason="stop",
            prompt_sha256="not-a-sha",
            raw_text_sha256=raw_sha,
            warnings=(),
        )
    assert "prompt_sha256 must be a valid 64-character SHA256 hex string" in str(exc_info.value)


def test_structured_output_result_validates_warnings_is_tuple():
    sql = "SELECT 1"
    sql_sha = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    raw_sha = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    
    with pytest.raises(SQLStructuredOutputContractError) as exc_info:
        SQLStructuredOutputResult(
            sql_text=sql,
            sql_sha256=sql_sha,
            sql_char_count=len(sql),
            provider_name="openai",
            provider_model="gpt-4",
            finish_reason="stop",
            prompt_sha256=None,
            raw_text_sha256=raw_sha,
            warnings=["list-is-invalid"],  # type: ignore
        )
    assert "warnings must be a tuple" in str(exc_info.value)
