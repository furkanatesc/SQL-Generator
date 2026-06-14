import hashlib
from dataclasses import dataclass, field
from typing import Tuple
from app.sql_generation import SQLGenerationConstraint, SQLGenerationProviderContractError

SQL_PROMPT_BUILDER_VERSION = "sql_prompt_builder_v2"

SUPPORTED_DIALECTS = {"sqlite", "postgresql", "oracle"}


@dataclass(frozen=True)
class SQLPromptBuilderConfig:
    target_dialect: str
    max_prompt_chars: int = 30000
    require_sql_only_output: bool = True
    allow_dml: bool = False
    allow_ddl: bool = False

    def __post_init__(self) -> None:
        if not self.target_dialect:
            raise SQLGenerationProviderContractError("target_dialect cannot be empty.")
        if self.target_dialect not in SUPPORTED_DIALECTS:
            raise SQLGenerationProviderContractError(
                f"Unsupported dialect: '{self.target_dialect}'."
            )
        if self.max_prompt_chars <= 0:
            raise SQLGenerationProviderContractError(
                "max_prompt_chars must be a positive integer."
            )


@dataclass(frozen=True)
class SQLPromptBuilderSection:
    section_type: str
    title: str
    content_items: Tuple[str, ...]
    required: bool

    def __post_init__(self) -> None:
        if not self.section_type or not self.section_type.strip():
            raise SQLGenerationProviderContractError("section_type cannot be empty.")
        if not self.title or not self.title.strip():
            raise SQLGenerationProviderContractError("title cannot be empty.")
        if self.required and not self.content_items:
            raise SQLGenerationProviderContractError(
                f"Section '{self.section_type}' is required but has no content items."
            )


@dataclass(frozen=True)
class SQLPromptBuilderResult:
    target_dialect: str
    prompt_text: str
    prompt_sha256: str
    prompt_char_count: int
    sections: Tuple[SQLPromptBuilderSection, ...]
    section_types: Tuple[str, ...]
    source_item_ids: Tuple[str, ...]
    constraints: Tuple[SQLGenerationConstraint, ...]
    version: str = SQL_PROMPT_BUILDER_VERSION

    def __post_init__(self) -> None:
        if self.version != SQL_PROMPT_BUILDER_VERSION:
            raise SQLGenerationProviderContractError(
                f"Invalid result version: '{self.version}'. Expected '{SQL_PROMPT_BUILDER_VERSION}'."
            )
        if not self.target_dialect or self.target_dialect not in SUPPORTED_DIALECTS:
            raise SQLGenerationProviderContractError(
                f"Unsupported target dialect: '{self.target_dialect}'."
            )
        if not self.prompt_text or not self.prompt_text.strip():
            raise SQLGenerationProviderContractError("prompt_text cannot be empty.")
        
        expected_sha = hashlib.sha256(self.prompt_text.encode("utf-8")).hexdigest()
        if self.prompt_sha256 != expected_sha:
            raise SQLGenerationProviderContractError(
                "prompt_sha256 does not match the actual SHA256 of prompt_text."
            )
        if self.prompt_char_count != len(self.prompt_text):
            raise SQLGenerationProviderContractError(
                "prompt_char_count does not match the actual length of prompt_text."
            )
        if not self.sections:
            raise SQLGenerationProviderContractError("sections list cannot be empty.")
        
        # Verify that all section types match
        expected_section_types = tuple(s.section_type for s in self.sections)
        if self.section_types != expected_section_types:
            raise SQLGenerationProviderContractError(
                "section_types must match the types of the provided sections."
            )
