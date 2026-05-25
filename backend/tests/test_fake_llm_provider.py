from app.llm.fake_provider import DeterministicFakeLLMProvider
from app.llm.provider import LLMProvider, SQLGenerationRequest, SQLGenerationResponse


def test_deterministic_fake_llm_provider_returns_contract_response():
    provider = DeterministicFakeLLMProvider(sql="SELECT * FROM customers")
    request = SQLGenerationRequest(
        prompt="Show customers",
        dialect="postgres",
        purpose="writer",
    )

    response = provider.generate_sql(request)

    assert isinstance(provider, LLMProvider)
    assert isinstance(response, SQLGenerationResponse)
    assert response.sql == "SELECT * FROM customers"
    assert response.provider_name == "fake"
    assert response.model_name == "deterministic-fake"
    assert response.raw_output == "SELECT * FROM customers"
    assert response.metadata["dialect"] == "postgres"
    assert response.metadata["purpose"] == "writer"
