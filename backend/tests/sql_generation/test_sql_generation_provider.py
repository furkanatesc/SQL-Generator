import socket
import pytest
import hashlib
from app.sql_generation.sql_generation_input_contract import SQLGenerationInputResult
from app.sql_generation.sql_generation_provider_contract import (
    SQLGenerationProviderRequest,
    SQLGenerationProviderResponse,
    SQLGenerationProviderContractError,
    SQL_GENERATION_PROVIDER_VERSION
)
from app.sql_generation.sql_generation_provider import DeterministicFakeSQLGenerationProvider
from app.sql_generation.sql_generation_provider_runner import SQLGenerationProviderRunner

VALID_SQL = "SELECT 1;"
VALID_SHA = hashlib.sha256(VALID_SQL.encode("utf-8")).hexdigest()
VALID_OUTPUT_SHA = VALID_SHA


def build_provider_request(prompt: str = VALID_SQL, prompt_sha256: str | None = None, provider_id: str = "fake-provider", model_id: str = "fake-model") -> SQLGenerationProviderRequest:
    actual_sha = prompt_sha256 or hashlib.sha256(prompt.encode("utf-8")).hexdigest()
    return SQLGenerationProviderRequest(
        version="sql_generation_provider_v1",
        input_version="sql_generation_input_v1",
        query_id="q-id",
        prompt=prompt,
        prompt_sha256=actual_sha,
        target_dialect="sqlite",
        constraints=(),
        provider_id=provider_id,
        model_id=model_id,
        temperature=0.0,
        max_output_tokens=100,
        metadata={},
    )


def test_fake_provider_is_deterministic_for_same_request():
    provider = DeterministicFakeSQLGenerationProvider(fixed_sql=VALID_SQL)
    req = build_provider_request()
    resp1 = provider.generate(req)
    resp2 = provider.generate(req)
    assert resp1 == resp2


def test_fake_provider_preserves_prompt_sha256():
    provider = DeterministicFakeSQLGenerationProvider()
    req = build_provider_request(prompt_sha256=VALID_SHA)
    resp = provider.generate(req)
    assert resp.prompt_sha256 == VALID_SHA


def test_fake_provider_sets_provider_and_model_id():
    provider = DeterministicFakeSQLGenerationProvider()
    req = build_provider_request(provider_id="custom-provider", model_id="custom-model")
    resp = provider.generate(req)
    assert resp.provider_id == "custom-provider"
    assert resp.model_id == "custom-model"


def test_fake_provider_sets_finish_reason_stop():
    provider = DeterministicFakeSQLGenerationProvider()
    req = build_provider_request()
    resp = provider.generate(req)
    assert resp.finish_reason == "stop"


def test_fake_provider_computes_output_sha256():
    sql = "SELECT name FROM users WHERE id = 5;"
    provider = DeterministicFakeSQLGenerationProvider(fixed_sql=sql)
    req = build_provider_request()
    resp = provider.generate(req)
    expected_output_sha = hashlib.sha256(sql.encode("utf-8")).hexdigest()
    assert resp.output_sha256 == expected_output_sha


def test_provider_runner_maps_input_result_to_request():
    prompt = "system: prompt"
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    input_result = SQLGenerationInputResult(
        raw_query="list users",
        normalized_query="list users",
        intent_type="list",
        target_dialect="sqlite",
        rendered_prompt=prompt,
        prompt_sha256=prompt_hash,
        prompt_char_count=14,
        constraints=(),
        source_section_types=("system_instructions",),
        source_item_ids=("table:users",),
    )

    runner = SQLGenerationProviderRunner()
    provider = DeterministicFakeSQLGenerationProvider()
    result = runner.run(
        input_result=input_result,
        provider=provider,
        provider_id="fake-sql-provider",
        model_id="deterministic-fake-v1",
        temperature=0.0,
        max_output_tokens=100,
        metadata={"user_id": "u45"},
        query_id="query-123",
    )

    # Asserts request mapping
    req = result.request
    assert req.version == SQL_GENERATION_PROVIDER_VERSION
    assert req.input_version == input_result.input_version
    assert req.prompt == input_result.rendered_prompt
    assert req.prompt_sha256 == input_result.prompt_sha256
    assert req.target_dialect == input_result.target_dialect
    assert req.provider_id == "fake-sql-provider"
    assert req.model_id == "deterministic-fake-v1"
    assert req.temperature == 0.0
    assert req.max_output_tokens == 100
    assert req.metadata == {"user_id": "u45"}
    assert req.query_id == "query-123"


def test_provider_runner_returns_versioned_result():
    prompt = "system: prompt"
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    input_result = SQLGenerationInputResult(
        raw_query="list users",
        normalized_query="list users",
        intent_type="list",
        target_dialect="sqlite",
        rendered_prompt=prompt,
        prompt_sha256=prompt_hash,
        prompt_char_count=14,
        constraints=(),
        source_section_types=("system_instructions",),
        source_item_ids=("table:users",),
    )

    runner = SQLGenerationProviderRunner()
    provider = DeterministicFakeSQLGenerationProvider()
    result = runner.run(
        input_result=input_result,
        provider=provider,
        provider_id="fake-sql-provider",
        model_id="deterministic-fake-v1",
    )
    assert result.version == SQL_GENERATION_PROVIDER_VERSION


def test_provider_runner_rejects_response_prompt_hash_mismatch():
    prompt = "system: prompt"
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    input_result = SQLGenerationInputResult(
        raw_query="list users",
        normalized_query="list users",
        intent_type="list",
        target_dialect="sqlite",
        rendered_prompt=prompt,
        prompt_sha256=prompt_hash,
        prompt_char_count=14,
        constraints=(),
        source_section_types=("system_instructions",),
        source_item_ids=("table:users",),
    )

    # Create a provider that alters response prompt_sha256
    class BuggyProvider:
        def generate(self, request: SQLGenerationProviderRequest) -> SQLGenerationProviderResponse:
            return SQLGenerationProviderResponse(
                version=SQL_GENERATION_PROVIDER_VERSION,
                provider_id=request.provider_id,
                model_id=request.model_id,
                raw_text=VALID_SQL,
                finish_reason="stop",
                prompt_sha256="b" * 64,  # Mismatch!
                output_sha256=VALID_OUTPUT_SHA,
                latency_ms=10,
                token_usage=None,
                metadata={},
            )

    runner = SQLGenerationProviderRunner()
    provider = BuggyProvider()
    with pytest.raises(SQLGenerationProviderContractError, match="Integrity check failed: Response prompt SHA256"):
        runner.run(
            input_result=input_result,
            provider=provider,  # type: ignore
            provider_id="fake-sql-provider",
            model_id="deterministic-fake-v1",
        )


def test_provider_runner_rejects_provider_id_mismatch():
    prompt = "system: prompt"
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    input_result = SQLGenerationInputResult(
        raw_query="list users",
        normalized_query="list users",
        intent_type="list",
        target_dialect="sqlite",
        rendered_prompt=prompt,
        prompt_sha256=prompt_hash,
        prompt_char_count=14,
        constraints=(),
        source_section_types=("system_instructions",),
        source_item_ids=("table:users",),
    )

    class MismatchedProvider:
        def generate(self, request: SQLGenerationProviderRequest) -> SQLGenerationProviderResponse:
            return SQLGenerationProviderResponse(
                version=SQL_GENERATION_PROVIDER_VERSION,
                provider_id="wrong-provider",  # Mismatched!
                model_id=request.model_id,
                raw_text=VALID_SQL,
                finish_reason="stop",
                prompt_sha256=request.prompt_sha256,
                output_sha256=VALID_OUTPUT_SHA,
                latency_ms=10,
                token_usage=None,
                metadata={},
            )

    runner = SQLGenerationProviderRunner()
    provider = MismatchedProvider()
    with pytest.raises(SQLGenerationProviderContractError, match="Response provider ID .* mismatches Request provider ID"):
        runner.run(
            input_result=input_result,
            provider=provider,  # type: ignore
            provider_id="fake-sql-provider",
            model_id="deterministic-fake-v1",
        )


def test_provider_runner_rejects_model_id_mismatch():
    prompt = "system: prompt"
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    input_result = SQLGenerationInputResult(
        raw_query="list users",
        normalized_query="list users",
        intent_type="list",
        target_dialect="sqlite",
        rendered_prompt=prompt,
        prompt_sha256=prompt_hash,
        prompt_char_count=14,
        constraints=(),
        source_section_types=("system_instructions",),
        source_item_ids=("table:users",),
    )

    class MismatchedProvider:
        def generate(self, request: SQLGenerationProviderRequest) -> SQLGenerationProviderResponse:
            return SQLGenerationProviderResponse(
                version=SQL_GENERATION_PROVIDER_VERSION,
                provider_id=request.provider_id,
                model_id="wrong-model",  # Mismatched!
                raw_text=VALID_SQL,
                finish_reason="stop",
                prompt_sha256=request.prompt_sha256,
                output_sha256=VALID_OUTPUT_SHA,
                latency_ms=10,
                token_usage=None,
                metadata={},
            )

    runner = SQLGenerationProviderRunner()
    provider = MismatchedProvider()
    with pytest.raises(SQLGenerationProviderContractError, match="Response model ID .* mismatches Request model ID"):
        runner.run(
            input_result=input_result,
            provider=provider,  # type: ignore
            provider_id="fake-sql-provider",
            model_id="deterministic-fake-v1",
        )


def test_provider_runner_rejects_input_prompt_sha_mismatch():
    input_result = SQLGenerationInputResult(
        raw_query="list users",
        normalized_query="list users",
        intent_type="list",
        target_dialect="sqlite",
        rendered_prompt="system: prompt",
        prompt_sha256="b" * 64,  # Mismatched SHA!
        prompt_char_count=14,
        constraints=(),
        source_section_types=("system_instructions",),
        source_item_ids=("table:users",),
    )

    runner = SQLGenerationProviderRunner()
    provider = DeterministicFakeSQLGenerationProvider()
    with pytest.raises(SQLGenerationProviderContractError, match="prompt_sha256 does not match"):
        runner.run(
            input_result=input_result,
            provider=provider,
            provider_id="fake-sql-provider",
            model_id="deterministic-fake-v1",
        )


def test_no_network_provider_boundary(monkeypatch):
    def fail_network(*args, **kwargs):
        raise AssertionError("Network is forbidden in provider boundary tests")

    monkeypatch.setattr(socket, "create_connection", fail_network)

    prompt = "system: prompt"
    prompt_hash = hashlib.sha256(prompt.encode("utf-8")).hexdigest()

    input_result = SQLGenerationInputResult(
        raw_query="list users",
        normalized_query="list users",
        intent_type="list",
        target_dialect="sqlite",
        rendered_prompt=prompt,
        prompt_sha256=prompt_hash,
        prompt_char_count=14,
        constraints=(),
        source_section_types=("system_instructions",),
        source_item_ids=("table:users",),
    )
    runner = SQLGenerationProviderRunner()
    provider = DeterministicFakeSQLGenerationProvider(fixed_sql="SELECT * FROM users;")
    result = runner.run(
        input_result=input_result,
        provider=provider,
        provider_id="fake-sql-provider",
        model_id="deterministic-fake-v1",
    )
    assert result.generated_sql_text == "SELECT * FROM users;"
