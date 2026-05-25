from app.llm.provider import (
    LLMProvider,
    SQLGenerationRequest,
    SQLGenerationResponse,
)


class ContractFakeProvider:
    def generate_sql(self, request: SQLGenerationRequest) -> SQLGenerationResponse:
        return SQLGenerationResponse(
            sql="SELECT * FROM customers",
            provider_name="fake",
            model_name="fake-model",
            raw_output="SELECT * FROM customers",
            metadata={"dialect": request.dialect, "purpose": request.purpose},
        )


def test_sql_generation_request_contract_is_explicit():
    request = SQLGenerationRequest(
        prompt="Generate SQL",
        dialect="postgres",
        purpose="writer",
    )

    assert request.prompt == "Generate SQL"
    assert request.dialect == "postgres"
    assert request.purpose == "writer"
    assert request.metadata == {}


def test_sql_generation_response_contract_is_explicit():
    response = SQLGenerationResponse(
        sql="SELECT * FROM customers",
        provider_name="fake",
        model_name="fake-model",
        raw_output="raw",
        metadata={"finish_reason": "stop"},
    )

    assert response.sql == "SELECT * FROM customers"
    assert response.provider_name == "fake"
    assert response.model_name == "fake-model"
    assert response.raw_output == "raw"
    assert response.metadata == {"finish_reason": "stop"}


def test_provider_protocol_uses_request_response_contract():
    provider = ContractFakeProvider()
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
    assert response.metadata["dialect"] == "postgres"
    assert response.metadata["purpose"] == "writer"
