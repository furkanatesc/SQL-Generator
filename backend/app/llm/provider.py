from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMProvider(Protocol):
    def generate_sql(self, prompt: str) -> str:
        ...
