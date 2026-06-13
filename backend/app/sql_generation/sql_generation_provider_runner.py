import uuid
from typing import Mapping
from app.sql_generation.sql_generation_input_contract import SQLGenerationInputResult
from app.sql_generation.sql_generation_provider_contract import (
    SQLGenerationProviderRequest,
    SQLGenerationProviderResult,
    SQLGenerationProviderContractError,
    SQL_GENERATION_PROVIDER_VERSION
)
from app.sql_generation.sql_generation_provider import SQLGenerationProvider


class SQLGenerationProviderRunner:
    """
    Runner orchestrating the mapping from SQLGenerationInputResult to request,
    executing it via a provider, and compiling the final SQLGenerationProviderResult.
    """
    def run(
        self,
        input_result: SQLGenerationInputResult,
        provider: SQLGenerationProvider,
        provider_id: str,
        model_id: str,
        temperature: float = 0.0,
        max_output_tokens: int | None = None,
        metadata: Mapping[str, str] | None = None,
        query_id: str | None = None
    ) -> SQLGenerationProviderResult:

        # 1. Map to Provider Request DTO
        # Generate a unique query ID or use deterministic one
        resolved_query_id = query_id or str(uuid.uuid4())

        request = SQLGenerationProviderRequest(
            version=SQL_GENERATION_PROVIDER_VERSION,
            input_version=input_result.input_version,
            query_id=resolved_query_id,
            prompt=input_result.rendered_prompt,
            prompt_sha256=input_result.prompt_sha256,
            target_dialect=input_result.target_dialect,
            constraints=input_result.constraints,
            provider_id=provider_id,
            model_id=model_id,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            metadata=metadata or {}
        )

        # 2. Invoke model provider
        response = provider.generate(request)

        # 3. Fail-fast integrity validations
        if response.prompt_sha256 != request.prompt_sha256:
            raise SQLGenerationProviderContractError(
                f"Integrity check failed: Response prompt SHA256 '{response.prompt_sha256}' "
                f"mismatches Request prompt SHA256 '{request.prompt_sha256}'."
            )

        if response.provider_id != request.provider_id:
            raise SQLGenerationProviderContractError(
                f"Integrity check failed: Response provider ID '{response.provider_id}' "
                f"mismatches Request provider ID '{request.provider_id}'."
            )

        if response.model_id != request.model_id:
            raise SQLGenerationProviderContractError(
                f"Integrity check failed: Response model ID '{response.model_id}' "
                f"mismatches Request model ID '{request.model_id}'."
            )

        # 4. Extract generated SQL text
        generated_sql_text = response.raw_text

        # 5. Build and return consolidated result
        return SQLGenerationProviderResult(
            version=SQL_GENERATION_PROVIDER_VERSION,
            request=request,
            response=response,
            generated_sql_text=generated_sql_text,
            prompt_sha256=request.prompt_sha256,
            output_sha256=response.output_sha256
        )
