import pytest
import hashlib
from dataclasses import FrozenInstanceError
from app.prompting.sql_prompt_builder_contract import (
    SQL_PROMPT_BUILDER_VERSION,
    SQLPromptBuilderConfig,
    SQLPromptBuilderSection,
    SQLPromptBuilderResult,
    SQLPromptBuilderContractError
)
from app.sql_generation import SQLGenerationConstraint


def test_sql_prompt_builder_version_is_v2():
    assert SQL_PROMPT_BUILDER_VERSION == "sql_prompt_builder_v2"


def test_prompt_builder_config_is_frozen():
    config = SQLPromptBuilderConfig(target_dialect="sqlite")
    assert config.target_dialect == "sqlite"
    
    with pytest.raises(FrozenInstanceError):
        config.target_dialect = "postgresql"  # type: ignore


def test_prompt_builder_section_is_frozen():
    section = SQLPromptBuilderSection(
        section_type="system_rules",
        title="System Rules",
        content_items=("rule1",),
        required=True
    )
    assert section.section_type == "system_rules"
    
    with pytest.raises(FrozenInstanceError):
        section.section_type = "dialect_rules"  # type: ignore


def test_prompt_builder_result_is_frozen():
    system_sec = SQLPromptBuilderSection(
        section_type="system_rules",
        title="System Rules",
        content_items=("rule1",),
        required=True
    )
    dialect_sec = SQLPromptBuilderSection(
        section_type="dialect_rules",
        title="Dialect Rules",
        content_items=("rule2",),
        required=True
    )
    schema_sec = SQLPromptBuilderSection(
        section_type="schema_context",
        title="Schema Context",
        content_items=("rule3",),
        required=True
    )
    rel_sec = SQLPromptBuilderSection(
        section_type="relationship_context",
        title="Relationship Context",
        content_items=(),
        required=False
    )
    user_sec = SQLPromptBuilderSection(
        section_type="user_intent",
        title="User Intent",
        content_items=("rule4",),
        required=True
    )
    gen_sec = SQLPromptBuilderSection(
        section_type="generation_constraints",
        title="Generation Constraints",
        content_items=("rule5",),
        required=True
    )
    output_sec = SQLPromptBuilderSection(
        section_type="output_contract",
        title="Output Contract",
        content_items=("rule6",),
        required=True
    )
    
    sections = (
        system_sec,
        dialect_sec,
        schema_sec,
        rel_sec,
        user_sec,
        gen_sec,
        output_sec
    )
    
    text = (
        "## System Rules\n- rule1\n\n"
        "## Dialect Rules\n- rule2\n\n"
        "## Schema Context\n- rule3\n\n"
        "## Relationship Context\n\n"
        "## User Intent\n- rule4\n\n"
        "## Generation Constraints\n- rule5\n\n"
        "## Output Contract\n- rule6"
    )
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    
    result = SQLPromptBuilderResult(
        target_dialect="sqlite",
        prompt_text=text,
        prompt_sha256=sha,
        prompt_char_count=len(text),
        sections=sections,
        section_types=tuple(s.section_type for s in sections),
        source_item_ids=("item1",),
        constraints=(SQLGenerationConstraint("name", "val"),),
        version=SQL_PROMPT_BUILDER_VERSION
    )
    
    assert result.target_dialect == "sqlite"
    with pytest.raises(FrozenInstanceError):
        result.target_dialect = "postgresql"  # type: ignore


def test_prompt_builder_result_rejects_noncanonical_section_order():
    system_sec = SQLPromptBuilderSection(
        section_type="system_rules",
        title="System Rules",
        content_items=("rule1",),
        required=True
    )
    dialect_sec = SQLPromptBuilderSection(
        section_type="dialect_rules",
        title="Dialect Rules",
        content_items=("rule2",),
        required=True
    )
    
    # We leave out other required sections and order them arbitrarily
    sections = (dialect_sec, system_sec)
    text = "## Dialect Rules\n- rule2\n\n## System Rules\n- rule1"
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    
    with pytest.raises(SQLPromptBuilderContractError) as exc_info:
        SQLPromptBuilderResult(
            target_dialect="sqlite",
            prompt_text=text,
            prompt_sha256=sha,
            prompt_char_count=len(text),
            sections=sections,
            section_types=tuple(s.section_type for s in sections),
            source_item_ids=("item1",),
            constraints=(SQLGenerationConstraint("name", "val"),),
            version=SQL_PROMPT_BUILDER_VERSION
        )
    assert "canonical V2 order" in str(exc_info.value)
