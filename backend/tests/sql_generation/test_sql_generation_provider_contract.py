import dataclasses
import hashlib
import pytest
from app.sql_generation.sql_generation_provider_contract import (
    SQL_GENERATION_PROVIDER_VERSION,
    SQLGenerationTokenUsage,
    SQLGenerationProviderRequest,
    SQLGenerationProviderResponse,
    SQLGenerationProviderResult,
    SQLGenerationProviderContractError,
)

VALID_PROMPT = "prompt text"
VALID_SHA = hashlib.sha256(VALID_PROMPT.encode("utf-8")).hexdigest()
VALID_SQL = "SELECT 1;"
VALID_OUTPUT_SHA = hashlib.sha256(VALID_SQL.encode("utf-8")).hexdigest()


def test_sql_generation_provider_version_is_v1():
    assert SQL_GENERATION_PROVIDER_VERSION == "sql_generation_provider_v1"


def test_provider_request_is_frozen():
    req = SQLGenerationProviderRequest(
        version="sql_generation_provider_v1",
        input_version="sql_generation_input_v1",
        query_id="q1",
        prompt=VALID_PROMPT,
        prompt_sha256=VALID_SHA,
        target_dialect="sqlite",
        constraints=(),
        provider_id="fake",
        model_id="fake-v1",
        temperature=0.0,
        max_output_tokens=100,
        metadata={},
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        req.temperature = 1.0  # type: ignore


def test_provider_response_is_frozen():
    resp = SQLGenerationProviderResponse(
        version="sql_generation_provider_v1",
        provider_id="fake",
        model_id="fake-v1",
        raw_text=VALID_SQL,
        finish_reason="stop",
        prompt_sha256=VALID_SHA,
        output_sha256=VALID_OUTPUT_SHA,
        latency_ms=10,
        token_usage=None,
        metadata={},
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        resp.finish_reason = "length"  # type: ignore


def test_provider_result_is_frozen():
    req = SQLGenerationProviderRequest(
        version="sql_generation_provider_v1",
        input_version="sql_generation_input_v1",
        query_id="q1",
        prompt=VALID_PROMPT,
        prompt_sha256=VALID_SHA,
        target_dialect="sqlite",
        constraints=(),
        provider_id="fake",
        model_id="fake-v1",
        temperature=0.0,
        max_output_tokens=100,
        metadata={},
    )
    resp = SQLGenerationProviderResponse(
        version="sql_generation_provider_v1",
        provider_id="fake",
        model_id="fake-v1",
        raw_text=VALID_SQL,
        finish_reason="stop",
        prompt_sha256=VALID_SHA,
        output_sha256=VALID_OUTPUT_SHA,
        latency_ms=10,
        token_usage=None,
        metadata={},
    )
    res = SQLGenerationProviderResult(
        version="sql_generation_provider_v1",
        request=req,
        response=resp,
        generated_sql_text=VALID_SQL,
        prompt_sha256=VALID_SHA,
        output_sha256=VALID_OUTPUT_SHA,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        res.generated_sql_text = "SELECT 2;"  # type: ignore


def test_provider_request_rejects_empty_prompt():
    with pytest.raises(SQLGenerationProviderContractError, match="Prompt cannot be empty."):
        SQLGenerationProviderRequest(
            version="sql_generation_provider_v1",
            input_version="sql_generation_input_v1",
            query_id="q1",
            prompt="  ",
            prompt_sha256=VALID_SHA,
            target_dialect="sqlite",
            constraints=(),
            provider_id="fake",
            model_id="fake-v1",
            temperature=0.0,
            max_output_tokens=100,
            metadata={},
        )


def test_provider_request_rejects_empty_provider_id():
    with pytest.raises(SQLGenerationProviderContractError, match="Provider ID cannot be empty."):
        SQLGenerationProviderRequest(
            version="sql_generation_provider_v1",
            input_version="sql_generation_input_v1",
            query_id="q1",
            prompt=VALID_PROMPT,
            prompt_sha256=VALID_SHA,
            target_dialect="sqlite",
            constraints=(),
            provider_id="",
            model_id="fake-v1",
            temperature=0.0,
            max_output_tokens=100,
            metadata={},
        )


def test_provider_request_rejects_empty_model_id():
    with pytest.raises(SQLGenerationProviderContractError, match="Model ID cannot be empty."):
        SQLGenerationProviderRequest(
            version="sql_generation_provider_v1",
            input_version="sql_generation_input_v1",
            query_id="q1",
            prompt=VALID_PROMPT,
            prompt_sha256=VALID_SHA,
            target_dialect="sqlite",
            constraints=(),
            provider_id="fake",
            model_id="  ",
            temperature=0.0,
            max_output_tokens=100,
            metadata={},
        )


def test_provider_request_rejects_invalid_temperature():
    with pytest.raises(SQLGenerationProviderContractError, match="Invalid temperature: 2.1"):
        SQLGenerationProviderRequest(
            version="sql_generation_provider_v1",
            input_version="sql_generation_input_v1",
            query_id="q1",
            prompt=VALID_PROMPT,
            prompt_sha256=VALID_SHA,
            target_dialect="sqlite",
            constraints=(),
            provider_id="fake",
            model_id="fake-v1",
            temperature=2.1,
            max_output_tokens=100,
            metadata={},
        )

    with pytest.raises(SQLGenerationProviderContractError, match="Invalid temperature: -0.1"):
        SQLGenerationProviderRequest(
            version="sql_generation_provider_v1",
            input_version="sql_generation_input_v1",
            query_id="q1",
            prompt=VALID_PROMPT,
            prompt_sha256=VALID_SHA,
            target_dialect="sqlite",
            constraints=(),
            provider_id="fake",
            model_id="fake-v1",
            temperature=-0.1,
            max_output_tokens=100,
            metadata={},
        )


def test_provider_request_rejects_wrong_version():
    with pytest.raises(SQLGenerationProviderContractError, match="Invalid request version"):
        SQLGenerationProviderRequest(
            version="sql_generation_provider_v2",
            input_version="sql_generation_input_v1",
            query_id="q1",
            prompt=VALID_PROMPT,
            prompt_sha256=VALID_SHA,
            target_dialect="sqlite",
            constraints=(),
            provider_id="fake",
            model_id="fake-v1",
            temperature=0.0,
            max_output_tokens=100,
            metadata={},
        )


def test_provider_response_rejects_wrong_version():
    with pytest.raises(SQLGenerationProviderContractError, match="Invalid response version"):
        SQLGenerationProviderResponse(
            version="sql_generation_provider_v2",
            provider_id="fake",
            model_id="fake-v1",
            raw_text=VALID_SQL,
            finish_reason="stop",
            prompt_sha256=VALID_SHA,
            output_sha256=VALID_OUTPUT_SHA,
            latency_ms=10,
            token_usage=None,
            metadata={},
        )


def test_provider_result_rejects_wrong_version():
    req = SQLGenerationProviderRequest(
        version="sql_generation_provider_v1",
        input_version="sql_generation_input_v1",
        query_id="q1",
        prompt=VALID_PROMPT,
        prompt_sha256=VALID_SHA,
        target_dialect="sqlite",
        constraints=(),
        provider_id="fake",
        model_id="fake-v1",
        temperature=0.0,
        max_output_tokens=100,
        metadata={},
    )
    resp = SQLGenerationProviderResponse(
        version="sql_generation_provider_v1",
        provider_id="fake",
        model_id="fake-v1",
        raw_text=VALID_SQL,
        finish_reason="stop",
        prompt_sha256=VALID_SHA,
        output_sha256=VALID_OUTPUT_SHA,
        latency_ms=10,
        token_usage=None,
        metadata={},
    )
    with pytest.raises(SQLGenerationProviderContractError, match="Invalid result version"):
        SQLGenerationProviderResult(
            version="sql_generation_provider_v2",
            request=req,
            response=resp,
            generated_sql_text=VALID_SQL,
            prompt_sha256=VALID_SHA,
            output_sha256=VALID_OUTPUT_SHA,
        )


def test_provider_response_rejects_output_sha_mismatch():
    with pytest.raises(SQLGenerationProviderContractError, match="output_sha256 does not match"):
        SQLGenerationProviderResponse(
            version="sql_generation_provider_v1",
            provider_id="fake",
            model_id="fake-v1",
            raw_text=VALID_SQL,
            finish_reason="stop",
            prompt_sha256=VALID_SHA,
            output_sha256="b" * 64,  # Mismatched Output SHA
            latency_ms=10,
            token_usage=None,
            metadata={},
        )


def test_provider_request_metadata_is_immutable():
    req = SQLGenerationProviderRequest(
        version="sql_generation_provider_v1",
        input_version="sql_generation_input_v1",
        query_id="q1",
        prompt=VALID_PROMPT,
        prompt_sha256=VALID_SHA,
        target_dialect="sqlite",
        constraints=(),
        provider_id="fake",
        model_id="fake-v1",
        temperature=0.0,
        max_output_tokens=100,
        metadata={"user_id": "u123"},
    )
    with pytest.raises(TypeError):
        req.metadata["user_id"] = "changed"  # type: ignore


def test_provider_response_metadata_is_immutable():
    resp = SQLGenerationProviderResponse(
        version="sql_generation_provider_v1",
        provider_id="fake",
        model_id="fake-v1",
        raw_text=VALID_SQL,
        finish_reason="stop",
        prompt_sha256=VALID_SHA,
        output_sha256=VALID_OUTPUT_SHA,
        latency_ms=10,
        token_usage=None,
        metadata={"session_id": "s123"},
    )
    with pytest.raises(TypeError):
        resp.metadata["session_id"] = "changed"  # type: ignore


def test_token_usage_validation_negative_tokens():
    with pytest.raises(SQLGenerationProviderContractError, match="Token counts cannot be negative."):
        SQLGenerationTokenUsage(prompt_tokens=-1, completion_tokens=5, total_tokens=4)


def test_token_usage_validation_mismatched_totals():
    with pytest.raises(SQLGenerationProviderContractError, match="total_tokens must equal"):
        SQLGenerationTokenUsage(prompt_tokens=10, completion_tokens=5, total_tokens=20)


def test_provider_request_rejects_prompt_sha_mismatch():
    with pytest.raises(SQLGenerationProviderContractError, match="prompt_sha256 does not match"):
        SQLGenerationProviderRequest(
            version="sql_generation_provider_v1",
            input_version="sql_generation_input_v1",
            query_id="q1",
            prompt=VALID_PROMPT,
            prompt_sha256="b" * 64,  # Mismatched SHA!
            target_dialect="sqlite",
            constraints=(),
            provider_id="fake",
            model_id="fake-v1",
            temperature=0.0,
            max_output_tokens=100,
            metadata={},
        )


def test_provider_result_rejects_generated_sql_text_mismatch():
    req = SQLGenerationProviderRequest(
        version="sql_generation_provider_v1",
        input_version="sql_generation_input_v1",
        query_id="q1",
        prompt=VALID_PROMPT,
        prompt_sha256=VALID_SHA,
        target_dialect="sqlite",
        constraints=(),
        provider_id="fake",
        model_id="fake-v1",
        temperature=0.0,
        max_output_tokens=100,
        metadata={},
    )
    resp = SQLGenerationProviderResponse(
        version="sql_generation_provider_v1",
        provider_id="fake",
        model_id="fake-v1",
        raw_text=VALID_SQL,
        finish_reason="stop",
        prompt_sha256=VALID_SHA,
        output_sha256=VALID_OUTPUT_SHA,
        latency_ms=10,
        token_usage=None,
        metadata={},
    )
    with pytest.raises(SQLGenerationProviderContractError, match="generated_sql_text must match"):
        SQLGenerationProviderResult(
            version="sql_generation_provider_v1",
            request=req,
            response=resp,
            generated_sql_text="SELECT 2;",  # Mismatched generated_sql_text!
            prompt_sha256=VALID_SHA,
            output_sha256=VALID_OUTPUT_SHA,
        )


def test_provider_response_rejects_negative_latency():
    with pytest.raises(SQLGenerationProviderContractError, match="latency_ms cannot be negative."):
        SQLGenerationProviderResponse(
            version="sql_generation_provider_v1",
            provider_id="fake",
            model_id="fake-v1",
            raw_text=VALID_SQL,
            finish_reason="stop",
            prompt_sha256=VALID_SHA,
            output_sha256=VALID_OUTPUT_SHA,
            latency_ms=-5,  # Mismatched latency!
            token_usage=None,
            metadata={},
        )


def test_provider_response_rejects_empty_raw_text():
    with pytest.raises(SQLGenerationProviderContractError, match="raw_text cannot be empty."):
        SQLGenerationProviderResponse(
            version="sql_generation_provider_v1",
            provider_id="fake",
            model_id="fake-v1",
            raw_text="   ",
            finish_reason="stop",
            prompt_sha256=VALID_SHA,
            output_sha256=VALID_OUTPUT_SHA,
            latency_ms=10,
            token_usage=None,
            metadata={},
        )

