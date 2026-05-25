from dataclasses import dataclass

from app.llm.provider import (
    LLMProvider,
    SQLGenerationRequest,
    SQLGenerationResponse,
)


@dataclass(frozen=True)
class DeterministicFakeLLMProvider:
    sql: str = "SELECT * FROM customers"
    provider_name: str = "fake"
    model_name: str = "deterministic-fake"

    def generate_sql(self, request: SQLGenerationRequest) -> SQLGenerationResponse:
        return SQLGenerationResponse(
            sql=self.sql,
            provider_name=self.provider_name,
            model_name=self.model_name,
            raw_output=self.sql,
            metadata={
                "dialect": request.dialect,
                "purpose": request.purpose,
            },
        )
