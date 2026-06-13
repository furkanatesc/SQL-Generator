import hashlib
import re
from dataclasses import dataclass
from typing import Mapping, Tuple
from types import MappingProxyType
from app.sql_generation.sql_generation_input_contract import SQLGenerationConstraint

SQL_GENERATION_PROVIDER_VERSION = "sql_generation_provider_v1"


def compute_sha256(text: str) -> str:
    """
    Computes the SHA256 hex digest of a given string.
    """
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_sha256_hex(value: str) -> bool:
    """
    Checks if a string is a valid 64-character SHA256 hex digest.
    """
    return bool(value and re.match(r"^[0-9a-fA-F]{64}$", value))


class SQLGenerationProviderContractError(ValueError):
    """
    Exception raised when contract invariants or validations are violated in the provider layer.
    """
    pass


@dataclass(frozen=True)
class SQLGenerationTokenUsage:
    """
    DTO encapsulating LLM output token details.
    """
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int

    def __post_init__(self) -> None:
        if self.prompt_tokens < 0 or self.completion_tokens < 0 or self.total_tokens < 0:
            raise SQLGenerationProviderContractError("Token counts cannot be negative.")
        if self.total_tokens != self.prompt_tokens + self.completion_tokens:
            raise SQLGenerationProviderContractError("total_tokens must equal prompt_tokens + completion_tokens.")


@dataclass(frozen=True)
class SQLGenerationProviderRequest:
    """
    DTO representing the final format of the prompt request sent to the provider.
    """
    version: str
    input_version: str
    query_id: str
    prompt: str
    prompt_sha256: str
    target_dialect: str
    constraints: Tuple[SQLGenerationConstraint, ...]
    provider_id: str
    model_id: str
    temperature: float
    max_output_tokens: int | None
    metadata: Mapping[str, str]

    def __post_init__(self) -> None:
        if self.version != SQL_GENERATION_PROVIDER_VERSION:
            raise SQLGenerationProviderContractError(
                f"Invalid request version: '{self.version}'. Expected '{SQL_GENERATION_PROVIDER_VERSION}'."
            )
        if not self.input_version or not self.input_version.strip():
            raise SQLGenerationProviderContractError("input_version cannot be empty.")
        if not self.query_id or not self.query_id.strip():
            raise SQLGenerationProviderContractError("query_id cannot be empty.")
        if not self.prompt or not self.prompt.strip():
            raise SQLGenerationProviderContractError("Prompt cannot be empty.")
        
        # Enforce that prompt_sha256 matches the actual SHA256 of prompt
        expected_prompt_sha = compute_sha256(self.prompt)
        if self.prompt_sha256 != expected_prompt_sha:
            raise SQLGenerationProviderContractError(
                "prompt_sha256 does not match the actual SHA256 of prompt."
            )

        if not self.target_dialect or not self.target_dialect.strip():
            raise SQLGenerationProviderContractError("target_dialect cannot be empty.")
        if not self.provider_id or not self.provider_id.strip():
            raise SQLGenerationProviderContractError("Provider ID cannot be empty.")
        if not self.model_id or not self.model_id.strip():
            raise SQLGenerationProviderContractError("Model ID cannot be empty.")
        if not (0.0 <= self.temperature <= 2.0):
            raise SQLGenerationProviderContractError(
                f"Invalid temperature: {self.temperature}. Must be between 0.0 and 2.0."
            )
        if self.max_output_tokens is not None and self.max_output_tokens <= 0:
            raise SQLGenerationProviderContractError("max_output_tokens must be positive.")

        # Ensure metadata keys and values are strings
        for k, v in self.metadata.items():
            if not isinstance(k, str) or not isinstance(v, str):
                raise SQLGenerationProviderContractError("Metadata keys and values must be strings.")

        # Shallow immutable mapping wrapper
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True)
class SQLGenerationProviderResponse:
    """
    DTO representing the structured output payload returned by the provider.
    """
    version: str
    provider_id: str
    model_id: str
    raw_text: str
    finish_reason: str
    prompt_sha256: str
    output_sha256: str
    latency_ms: int | None
    token_usage: SQLGenerationTokenUsage | None
    metadata: Mapping[str, str]

    def __post_init__(self) -> None:
        if self.version != SQL_GENERATION_PROVIDER_VERSION:
            raise SQLGenerationProviderContractError(
                f"Invalid response version: '{self.version}'. Expected '{SQL_GENERATION_PROVIDER_VERSION}'."
            )
        if not self.provider_id or not self.provider_id.strip():
            raise SQLGenerationProviderContractError("Provider ID cannot be empty.")
        if not self.model_id or not self.model_id.strip():
            raise SQLGenerationProviderContractError("Model ID cannot be empty.")
        if not self.raw_text or not self.raw_text.strip():
            raise SQLGenerationProviderContractError("raw_text cannot be empty.")
        if not self.finish_reason or not self.finish_reason.strip():
            raise SQLGenerationProviderContractError("Finish reason cannot be empty.")
        
        # Enforce hex format check for prompt hash
        if not is_sha256_hex(self.prompt_sha256):
            raise SQLGenerationProviderContractError("prompt_sha256 must be a 64-character hex string.")
            
        # Cryptographic check: Verify output_sha256 matches actual sha256 of raw_text
        expected_output_sha = compute_sha256(self.raw_text)
        if self.output_sha256 != expected_output_sha:
            raise SQLGenerationProviderContractError("output_sha256 does not match the actual SHA256 of raw_text.")

        if self.latency_ms is not None and self.latency_ms < 0:
            raise SQLGenerationProviderContractError("latency_ms cannot be negative.")

        # Ensure metadata keys and values are strings
        for k, v in self.metadata.items():
            if not isinstance(k, str) or not isinstance(v, str):
                raise SQLGenerationProviderContractError("Metadata keys and values must be strings.")

        # Shallow immutable mapping wrapper
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


@dataclass(frozen=True)
class SQLGenerationProviderResult:
    """
    Orchestration wrapper binding request, response, output metadata, and extracted query text.
    """
    version: str
    request: SQLGenerationProviderRequest
    response: SQLGenerationProviderResponse
    generated_sql_text: str
    prompt_sha256: str
    output_sha256: str

    def __post_init__(self) -> None:
        if self.version != SQL_GENERATION_PROVIDER_VERSION:
            raise SQLGenerationProviderContractError(
                f"Invalid result version: '{self.version}'. Expected '{SQL_GENERATION_PROVIDER_VERSION}'."
            )
        if self.generated_sql_text != self.response.raw_text:
            raise SQLGenerationProviderContractError(
                "generated_sql_text must match response.raw_text in provider boundary v1."
            )
        if self.prompt_sha256 != self.request.prompt_sha256:
            raise SQLGenerationProviderContractError("Prompt SHA256 mismatch between result and request.")
        if self.prompt_sha256 != self.response.prompt_sha256:
            raise SQLGenerationProviderContractError("Prompt SHA256 mismatch between result and response.")
        if self.output_sha256 != self.response.output_sha256:
            raise SQLGenerationProviderContractError("Output SHA256 mismatch between result and response.")
