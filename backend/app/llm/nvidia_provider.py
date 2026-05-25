from dataclasses import dataclass, field
from typing import Any, Mapping

from app.llm.provider import SQLGenerationRequest, SQLGenerationResponse
from app.llm_client import NVIDIAClient


@dataclass
class NVIDIAProvider:
    client: NVIDIAClient = field(default_factory=NVIDIAClient)
    provider_name: str = "nvidia"
    model_name: str | None = None
    api_key: str | None = None

    def generate_sql(self, request: SQLGenerationRequest) -> SQLGenerationResponse:
        sql = self.client.generate_sql(
            request.prompt,
            api_key=self.api_key,
        )

        model_name = self.model_name or getattr(self.client, "model", None)

        return SQLGenerationResponse(
            sql=sql,
            provider_name=self.provider_name,
            model_name=model_name,
            raw_output=sql,
            metadata={
                "dialect": request.dialect,
                "purpose": request.purpose,
            },
        )
