import sys

from app.llm.provider import LLMProvider


class FakeProvider:
    def generate_sql(self, prompt: str) -> str:
        return "SELECT * FROM customers"


def test_fake_provider_satisfies_llm_provider_protocol():
    provider = FakeProvider()
    assert isinstance(provider, LLMProvider)


def test_llm_provider_contract_returns_sql_string():
    provider = FakeProvider()
    result = provider.generate_sql("Show me customers")
    
    assert isinstance(result, str)
    assert result == "SELECT * FROM customers"


def test_llm_provider_interface_has_no_runtime_external_dependency():
    assert "app.llm.provider" in sys.modules
    
    # Provider can be instantiated and used without any env, config, or network.
    provider = FakeProvider()
    assert provider.generate_sql("some prompt") == "SELECT * FROM customers"
