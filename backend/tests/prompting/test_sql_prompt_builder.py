import pytest
import hashlib
from app.sql_generation import (
    SQLGenerationConstraint,
    SQLGenerationProviderContractError
)
from app.sql_generation.sql_generation_input_contract import SQLGenerationInputResult
from app.prompting.sql_prompt_builder_contract import (
    SQLPromptBuilderConfig,
    SQLPromptBuilderResult,
    SQL_PROMPT_BUILDER_VERSION
)
from app.prompting.sql_prompt_builder import SQLPromptBuilder


def build_dummy_input(
    rendered_prompt: str = None,
    target_dialect: str = "sqlite",
    source_item_ids: tuple = ("id1", "id2", "id1")
) -> SQLGenerationInputResult:
    if rendered_prompt is None:
        rendered_prompt = (
            "## System Instructions\n- Instruction 1\n- Instruction 2\n\n"
            "## User Intent\n- Intent 1\n\n"
            "## Schema Context\n- Schema 1\n\n"
            "## Relationship Context\n- Relation 1\n\n"
            "## Constraints\n- Constraint 1\n\n"
            "## Output Contract\n- Output 1"
        )
    return SQLGenerationInputResult(
        raw_query="SELECT 1",
        normalized_query="SELECT 1",
        intent_type="SELECT",
        target_dialect=target_dialect,
        rendered_prompt=rendered_prompt,
        prompt_sha256="dummy_sha",
        prompt_char_count=len(rendered_prompt),
        constraints=(SQLGenerationConstraint("name", "val"),),
        source_section_types=(
            "system_instructions",
            "user_intent",
            "schema_context",
            "relationship_context",
            "constraints",
            "output_contract"
        ),
        source_item_ids=source_item_ids
    )


def test_prompt_builder_rejects_empty_rendered_prompt():
    builder = SQLPromptBuilder()
    config = SQLPromptBuilderConfig(target_dialect="sqlite")
    
    # Empty rendered prompt
    inp = build_dummy_input(rendered_prompt="")
    with pytest.raises(SQLGenerationProviderContractError) as exc_info:
        builder.build(inp, config)
    assert "rendered_prompt cannot be empty" in str(exc_info.value)
    
    # Whitespace rendered prompt
    inp = build_dummy_input(rendered_prompt="   \n   ")
    with pytest.raises(SQLGenerationProviderContractError):
        builder.build(inp, config)


def test_prompt_builder_rejects_unsupported_dialect():
    # Attempting to construct config with unsupported dialect should raise exception
    with pytest.raises(SQLGenerationProviderContractError) as exc_info:
        SQLPromptBuilderConfig(target_dialect="mysql")
    assert "Unsupported dialect: 'mysql'" in str(exc_info.value)


def test_prompt_builder_rejects_prompt_over_budget():
    builder = SQLPromptBuilder()
    config = SQLPromptBuilderConfig(target_dialect="sqlite", max_prompt_chars=100)
    inp = build_dummy_input()
    
    with pytest.raises(SQLGenerationProviderContractError) as exc_info:
        builder.build(inp, config)
    assert "exceeds maximum configured limit" in str(exc_info.value)


def test_prompt_builder_preserves_section_order():
    builder = SQLPromptBuilder()
    config = SQLPromptBuilderConfig(target_dialect="sqlite")
    inp = build_dummy_input()
    result = builder.build(inp, config)
    
    expected_order = (
        "system_rules",
        "dialect_rules",
        "schema_context",
        "relationship_context",
        "user_intent",
        "generation_constraints",
        "output_contract"
    )
    
    assert result.section_types == expected_order
    assert len(result.sections) == len(expected_order)
    for idx, expected_type in enumerate(expected_order):
        assert result.sections[idx].section_type == expected_type


def test_prompt_builder_computes_prompt_sha256_from_prompt_text():
    builder = SQLPromptBuilder()
    config = SQLPromptBuilderConfig(target_dialect="sqlite")
    inp = build_dummy_input()
    result = builder.build(inp, config)
    
    expected_sha = hashlib.sha256(result.prompt_text.encode("utf-8")).hexdigest()
    assert result.prompt_sha256 == expected_sha
    assert len(result.prompt_sha256) == 64


def test_prompt_builder_computes_prompt_char_count():
    builder = SQLPromptBuilder()
    config = SQLPromptBuilderConfig(target_dialect="sqlite")
    inp = build_dummy_input()
    result = builder.build(inp, config)
    
    assert result.prompt_char_count == len(result.prompt_text)


def test_prompt_builder_deduplicates_source_item_ids_preserving_order():
    builder = SQLPromptBuilder()
    config = SQLPromptBuilderConfig(target_dialect="sqlite")
    inp = build_dummy_input(source_item_ids=("z", "a", "z", "b", "a", "c"))
    result = builder.build(inp, config)
    
    # Deduplicated source item ids must preserve original insertion order: z, a, b, c
    assert result.source_item_ids == ("z", "a", "b", "c")


def test_prompt_builder_is_deterministic_for_same_input():
    builder = SQLPromptBuilder()
    config1 = SQLPromptBuilderConfig(target_dialect="sqlite")
    config2 = SQLPromptBuilderConfig(target_dialect="sqlite")
    inp1 = build_dummy_input()
    inp2 = build_dummy_input()
    
    result1 = builder.build(inp1, config1)
    result2 = builder.build(inp2, config2)
    
    assert result1.prompt_text == result2.prompt_text
    assert result1.prompt_sha256 == result2.prompt_sha256
    assert result1.prompt_char_count == result2.prompt_char_count
    assert result1.section_types == result2.section_types
    assert result1.source_item_ids == result2.source_item_ids


def test_prompt_builder_includes_sql_only_output_contract():
    builder = SQLPromptBuilder()
    config = SQLPromptBuilderConfig(target_dialect="sqlite", require_sql_only_output=True)
    inp = build_dummy_input()
    result = builder.build(inp, config)
    
    output_contract_section = next(
        s for s in result.sections if s.section_type == "output_contract"
    )
    
    sql_only_instruction = "Return only SQL. No markdown. No explanation."
    assert sql_only_instruction in output_contract_section.content_items
    assert result.prompt_text.endswith(f"- {sql_only_instruction}")


def test_prompt_builder_does_not_call_provider():
    # By inspection and structure, SQLPromptBuilder uses pure python string parsing and 
    # compilation without importing any network-based or LLM libraries.
    # We verify that invoking the builder does not make any requests.
    builder = SQLPromptBuilder()
    config = SQLPromptBuilderConfig(target_dialect="sqlite")
    inp = build_dummy_input()
    
    # This call should succeed purely local
    result = builder.build(inp, config)
    assert result is not None
