from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol, runtime_checkable


@dataclass(frozen=True)
class SQLGenerationRequest:
    prompt: str
    dialect: str
    purpose: str
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SQLGenerationResponse:
    sql: str
    provider_name: str
    model_name: str | None = None
    raw_output: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@runtime_checkable
class LLMProvider(Protocol):
    def generate_sql(self, request: SQLGenerationRequest) -> SQLGenerationResponse:
        ...
