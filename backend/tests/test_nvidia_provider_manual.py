import os

import pytest

from app.llm.nvidia_provider import NVIDIAProvider
from app.llm.provider import SQLGenerationRequest


pytestmark = pytest.mark.manual_llm


@pytest.mark.skipif(
    os.getenv("RUN_MANUAL_LLM_TESTS") != "1",
    reason="manual real LLM test disabled by default",
)
def test_manual_nvidia_provider_real_call():
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        pytest.skip("NVIDIA_API_KEY is required for manual real LLM test")

    provider = NVIDIAProvider(api_key=api_key)

    response = provider.generate_sql(
        SQLGenerationRequest(
            prompt="Return only this SQL: SELECT 1",
            dialect="postgres",
            purpose="manual_smoke",
        )
    )

    assert isinstance(response.sql, str)
    assert response.sql.strip()
    assert response.provider_name == "nvidia"
