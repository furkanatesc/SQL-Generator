import pytest
from dataclasses import FrozenInstanceError
from app.prompting.sql_prompt_builder_contract import (
    SQL_PROMPT_BUILDER_VERSION,
    SQLPromptBuilderConfig,
    SQLPromptBuilderSection,
    SQLPromptBuilderResult
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
    section = SQLPromptBuilderSection(
        section_type="system_rules",
        title="System Rules",
        content_items=("rule1",),
        required=True
    )
    # compute valid sha256 to pass __post_init__ check
    import hashlib
    text = "## System Rules\n- rule1"
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    
    result = SQLPromptBuilderResult(
        target_dialect="sqlite",
        prompt_text=text,
        prompt_sha256=sha,
        prompt_char_count=len(text),
        sections=(section,),
        section_types=("system_rules",),
        source_item_ids=("item1",),
        constraints=(SQLGenerationConstraint("name", "val"),),
        version=SQL_PROMPT_BUILDER_VERSION
    )
    
    assert result.target_dialect == "sqlite"
    with pytest.raises(FrozenInstanceError):
        result.target_dialect = "postgresql"  # type: ignore
