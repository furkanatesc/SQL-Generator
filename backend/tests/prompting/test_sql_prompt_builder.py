import pytest
import hashlib
import socket
from app.sql_generation import SQLGenerationConstraint
from app.sql_generation.sql_generation_input_contract import SQLGenerationInputResult
from app.prompting.sql_prompt_builder_contract import (
    SQLPromptBuilderConfig,
    SQLPromptBuilderResult,
    SQLPromptBuilderContractError,
    SQL_PROMPT_BUILDER_VERSION
)
from app.prompting.sql_prompt_builder import SQLPromptBuilder


def build_dummy_input(
    rendered_prompt: str | None = None,
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
    
    prompt_sha256 = hashlib.sha256(rendered_prompt.encode("utf-8")).hexdigest()
    
    return SQLGenerationInputResult(
        raw_query="SELECT 1",
        normalized_query="SELECT 1",
        intent_type="SELECT",
        target_dialect=target_dialect,
        rendered_prompt=rendered_prompt,
        prompt_sha256=prompt_sha256,
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
    with pytest.raises(SQLPromptBuilderContractError) as exc_info:
        builder.build(inp, config)
    assert "rendered_prompt cannot be empty" in str(exc_info.value)
    
    # Whitespace rendered prompt
    inp = build_dummy_input(rendered_prompt="   \n   ")
    with pytest.raises(SQLPromptBuilderContractError):
        builder.build(inp, config)


def test_prompt_builder_rejects_unsupported_dialect():
    # Attempting to construct config with unsupported dialect should raise exception
    with pytest.raises(SQLPromptBuilderContractError) as exc_info:
        SQLPromptBuilderConfig(target_dialect="mysql")
    assert "Unsupported dialect: 'mysql'" in str(exc_info.value)


def test_prompt_builder_rejects_prompt_over_budget():
    builder = SQLPromptBuilder()
    config = SQLPromptBuilderConfig(target_dialect="sqlite", max_prompt_chars=100)
    inp = build_dummy_input()
    
    with pytest.raises(SQLPromptBuilderContractError) as exc_info:
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


def test_prompt_builder_rejects_input_prompt_sha_mismatch():
    builder = SQLPromptBuilder()
    config = SQLPromptBuilderConfig(target_dialect="sqlite")
    inp = build_dummy_input()
    
    # Tamper with the sha256 hash to simulate corruption
    corrupt_inp = SQLGenerationInputResult(
        raw_query=inp.raw_query,
        normalized_query=inp.normalized_query,
        intent_type=inp.intent_type,
        target_dialect=inp.target_dialect,
        rendered_prompt=inp.rendered_prompt,
        prompt_sha256="a" * 64,  # incorrect SHA
        prompt_char_count=inp.prompt_char_count,
        constraints=inp.constraints,
        source_section_types=inp.source_section_types,
        source_item_ids=inp.source_item_ids
    )
    
    with pytest.raises(SQLPromptBuilderContractError) as exc_info:
        builder.build(corrupt_inp, config)
    assert "prompt_sha256 does not match the actual SHA256" in str(exc_info.value)


def test_prompt_builder_rejects_input_prompt_char_count_mismatch():
    builder = SQLPromptBuilder()
    config = SQLPromptBuilderConfig(target_dialect="sqlite")
    inp = build_dummy_input()
    
    # Tamper with the char count to simulate corruption
    corrupt_inp = SQLGenerationInputResult(
        raw_query=inp.raw_query,
        normalized_query=inp.normalized_query,
        intent_type=inp.intent_type,
        target_dialect=inp.target_dialect,
        rendered_prompt=inp.rendered_prompt,
        prompt_sha256=inp.prompt_sha256,
        prompt_char_count=inp.prompt_char_count + 10,  # incorrect char count
        constraints=inp.constraints,
        source_section_types=inp.source_section_types,
        source_item_ids=inp.source_item_ids
    )
    
    with pytest.raises(SQLPromptBuilderContractError) as exc_info:
        builder.build(corrupt_inp, config)
    assert "prompt_char_count does not match the actual length" in str(exc_info.value)


def test_prompt_builder_rejects_target_dialect_mismatch():
    builder = SQLPromptBuilder()
    # config target_dialect=postgresql, input target_dialect=sqlite
    config = SQLPromptBuilderConfig(target_dialect="postgresql")
    inp = build_dummy_input(target_dialect="sqlite")
    
    with pytest.raises(SQLPromptBuilderContractError) as exc_info:
        builder.build(inp, config)
    assert "must match input_result.target_dialect" in str(exc_info.value)


def test_prompt_builder_preserves_non_bullet_section_content():
    builder = SQLPromptBuilder()
    config = SQLPromptBuilderConfig(target_dialect="sqlite")
    
    # System Instructions section contains flat text sentences that do not start with "- "
    flat_prompt = (
        "## System Instructions\nThis is a non-bullet plain text sentence.\nAnd another one.\n\n"
        "## User Intent\n- Intent 1\n\n"
        "## Schema Context\n- Schema 1\n\n"
        "## Relationship Context\n- Relation 1\n\n"
        "## Constraints\n- Constraint 1\n\n"
        "## Output Contract\n- Output 1"
    )
    inp = build_dummy_input(rendered_prompt=flat_prompt)
    result = builder.build(inp, config)
    
    system_rules_section = next(
        s for s in result.sections if s.section_type == "system_rules"
    )
    assert "This is a non-bullet plain text sentence." in system_rules_section.content_items
    assert "And another one." in system_rules_section.content_items


def test_prompt_builder_rejects_duplicate_required_sections():
    builder = SQLPromptBuilder()
    config = SQLPromptBuilderConfig(target_dialect="sqlite")
    
    # Prompt contains two "System Instructions" headers
    duplicate_prompt = (
        "## System Instructions\n- Instruction 1\n\n"
        "## System Instructions\n- Instruction 2\n\n"
        "## User Intent\n- Intent 1\n\n"
        "## Schema Context\n- Schema 1\n\n"
        "## Constraints\n- Constraint 1\n\n"
        "## Output Contract\n- Output 1"
    )
    inp = build_dummy_input(rendered_prompt=duplicate_prompt)
    with pytest.raises(SQLPromptBuilderContractError) as exc_info:
        builder.build(inp, config)
    assert "Duplicate section 'System Instructions'" in str(exc_info.value)


def test_prompt_builder_rejects_required_section_with_empty_content():
    builder = SQLPromptBuilder()
    config = SQLPromptBuilderConfig(target_dialect="sqlite")
    
    # Schema Context header has no bullets or plain text
    empty_section_prompt = (
        "## System Instructions\n- Instruction 1\n\n"
        "## User Intent\n- Intent 1\n\n"
        "## Schema Context\n\n"
        "## Constraints\n- Constraint 1\n\n"
        "## Output Contract\n- Output 1"
    )
    inp = build_dummy_input(rendered_prompt=empty_section_prompt)
    with pytest.raises(SQLPromptBuilderContractError) as exc_info:
        builder.build(inp, config)
    assert "Schema Context' cannot have empty content" in str(exc_info.value)


def test_prompt_builder_does_not_call_provider(monkeypatch):
    # Enforce network call block using monkeypatch on socket connection
    def block_socket_connect(*args, **kwargs):
        raise RuntimeError("Network/provider call attempted!")
    monkeypatch.setattr(socket.socket, "connect", block_socket_connect)
    
    builder = SQLPromptBuilder()
    config = SQLPromptBuilderConfig(target_dialect="sqlite")
    inp = build_dummy_input()
    
    result = builder.build(inp, config)
    assert result is not None
