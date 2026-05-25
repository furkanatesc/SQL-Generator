from app.llm.nvidia_provider import NVIDIAProvider
from app.llm.provider import LLMProvider, SQLGenerationRequest, SQLGenerationResponse


class FakeNVIDIAClient:
    model = "fake-nvidia-model"

    def __init__(self):
        self.calls = []

    def generate_sql(self, prompt: str, api_key: str | None = None) -> str:
        self.calls.append({"prompt": prompt, "api_key": api_key})
        return "SELECT * FROM customers"


def test_nvidia_provider_wraps_client_in_llm_contract():
    client = FakeNVIDIAClient()
    provider = NVIDIAProvider(client=client, api_key="test-key")

    request = SQLGenerationRequest(
        prompt="Generate SQL",
        dialect="postgres",
        purpose="writer",
    )

    response = provider.generate_sql(request)

    assert isinstance(provider, LLMProvider)
    assert isinstance(response, SQLGenerationResponse)
    assert response.sql == "SELECT * FROM customers"
    assert response.provider_name == "nvidia"
    assert response.model_name == "fake-nvidia-model"
    assert response.raw_output == "SELECT * FROM customers"
    assert response.metadata["dialect"] == "postgres"
    assert response.metadata["purpose"] == "writer"
    assert client.calls == [{"prompt": "Generate SQL", "api_key": "test-key"}]
