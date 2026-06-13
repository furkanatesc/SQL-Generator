import hashlib
from typing import Protocol, runtime_checkable
from app.sql_generation.sql_generation_provider_contract import (
    SQLGenerationProviderRequest,
    SQLGenerationProviderResponse,
    SQLGenerationTokenUsage,
    SQL_GENERATION_PROVIDER_VERSION
)


@runtime_checkable
class SQLGenerationProvider(Protocol):
    """
    Protocol/Interface defining standard model provider execution behavior.
    """
    def generate(
        self,
        request: SQLGenerationProviderRequest,
    ) -> SQLGenerationProviderResponse:
        ...


class DeterministicFakeSQLGenerationProvider:
    """
    Deterministic fake provider conforming to SQLGenerationProvider.
    Yields fixed/deterministic outcomes for unit testing and CI verification.
    """
    def __init__(self, fixed_sql: str = "SELECT 1;") -> None:
        self.fixed_sql = fixed_sql

    def generate(
        self,
        request: SQLGenerationProviderRequest
    ) -> SQLGenerationProviderResponse:
        raw_text = self.fixed_sql
        output_sha256 = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

        return SQLGenerationProviderResponse(
            version=SQL_GENERATION_PROVIDER_VERSION,
            provider_id=request.provider_id,
            model_id=request.model_id,
            raw_text=raw_text,
            finish_reason="stop",
            prompt_sha256=request.prompt_sha256,
            output_sha256=output_sha256,
            latency_ms=10,
            token_usage=SQLGenerationTokenUsage(
                prompt_tokens=10,
                completion_tokens=5,
                total_tokens=15
            ),
            metadata={}
        )
