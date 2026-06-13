import pytest
import hashlib
from app.prompting.prompt_render_contract import RenderedPromptResult, RenderedPromptSection
from app.sql_generation.sql_generation_input_contract import SQLGenerationInputConfig
from app.sql_generation.sql_generation_input_assembler import SQLGenerationInputAssembler
from app.retrieval.embedding_pipeline import EmbeddingNonRetryableError


def build_valid_rendered_sections():
    return (
        RenderedPromptSection(
            section_type="system_instructions",
            title="System Instructions",
            rendered_text="## System Instructions\n- Instruction 1",
            source_item_ids=(),
            required=True,
        ),
        RenderedPromptSection(
            section_type="user_intent",
            title="User Intent",
            rendered_text="## User Intent\n- Intent: list",
            source_item_ids=(),
            required=True,
        ),
        RenderedPromptSection(
            section_type="schema_context",
            title="Schema Context",
            rendered_text="## Schema Context\n- table: customers",
            source_item_ids=("table:customers", "column:customers.id"),
            required=True,
        ),
        RenderedPromptSection(
            section_type="relationship_context",
            title="Relationship Context",
            rendered_text="## Relationship Context",
            source_item_ids=(),
            required=True,
        ),
        RenderedPromptSection(
            section_type="constraints",
            title="Constraints",
            rendered_text="## Constraints\n- Constraint 1",
            source_item_ids=(),
            required=True,
        ),
        RenderedPromptSection(
            section_type="output_contract",
            title="Output Contract",
            rendered_text="## Output Contract\n- Output SQL",
            source_item_ids=(),
            required=True,
        ),
    )


def test_assembler_rejects_empty_raw_query():
    assembler = SQLGenerationInputAssembler()
    config = SQLGenerationInputConfig(target_dialect="sqlite")
    result = RenderedPromptResult(
        raw_query="  ",
        normalized_query="list customers",
        intent_type="list",
        rendered_prompt="prompt text",
        rendered_sections=build_valid_rendered_sections(),
    )
    with pytest.raises(EmbeddingNonRetryableError, match="Raw query cannot be empty."):
        assembler.assemble(result, config)


def test_assembler_rejects_empty_normalized_query():
    assembler = SQLGenerationInputAssembler()
    config = SQLGenerationInputConfig(target_dialect="sqlite")
    result = RenderedPromptResult(
        raw_query="list customers",
        normalized_query="",
        intent_type="list",
        rendered_prompt="prompt text",
        rendered_sections=build_valid_rendered_sections(),
    )
    with pytest.raises(EmbeddingNonRetryableError, match="Normalized query cannot be empty."):
        assembler.assemble(result, config)


def test_assembler_rejects_empty_intent_type():
    assembler = SQLGenerationInputAssembler()
    config = SQLGenerationInputConfig(target_dialect="sqlite")
    result = RenderedPromptResult(
        raw_query="list customers",
        normalized_query="list customers",
        intent_type=" ",
        rendered_prompt="prompt text",
        rendered_sections=build_valid_rendered_sections(),
    )
    with pytest.raises(EmbeddingNonRetryableError, match="Intent type cannot be empty."):
        assembler.assemble(result, config)


def test_assembler_rejects_empty_rendered_prompt():
    assembler = SQLGenerationInputAssembler()
    config = SQLGenerationInputConfig(target_dialect="sqlite")
    result = RenderedPromptResult(
        raw_query="list customers",
        normalized_query="list customers",
        intent_type="list",
        rendered_prompt="  ",
        rendered_sections=build_valid_rendered_sections(),
    )
    with pytest.raises(EmbeddingNonRetryableError, match="Rendered prompt cannot be empty."):
        assembler.assemble(result, config)


def test_assembler_rejects_empty_rendered_sections():
    assembler = SQLGenerationInputAssembler()
    config = SQLGenerationInputConfig(target_dialect="sqlite")
    result = RenderedPromptResult(
        raw_query="list customers",
        normalized_query="list customers",
        intent_type="list",
        rendered_prompt="prompt text",
        rendered_sections=(),
    )
    with pytest.raises(EmbeddingNonRetryableError, match="Rendered sections cannot be empty."):
        assembler.assemble(result, config)


def test_assembler_rejects_unsupported_target_dialect():
    assembler = SQLGenerationInputAssembler()
    config = SQLGenerationInputConfig(target_dialect="mysql")  # type: ignore
    result = RenderedPromptResult(
        raw_query="list customers",
        normalized_query="list customers",
        intent_type="list",
        rendered_prompt="prompt text",
        rendered_sections=build_valid_rendered_sections(),
    )
    with pytest.raises(EmbeddingNonRetryableError, match="Unsupported target dialect: 'mysql'"):
        assembler.assemble(result, config)


def test_assembler_rejects_non_positive_max_prompt_chars():
    assembler = SQLGenerationInputAssembler()
    config = SQLGenerationInputConfig(target_dialect="sqlite", max_prompt_chars=0)
    result = RenderedPromptResult(
        raw_query="list customers",
        normalized_query="list customers",
        intent_type="list",
        rendered_prompt="prompt text",
        rendered_sections=build_valid_rendered_sections(),
    )
    with pytest.raises(EmbeddingNonRetryableError, match="max_prompt_chars must be positive"):
        assembler.assemble(result, config)


def test_assembler_rejects_prompt_over_max_prompt_chars():
    assembler = SQLGenerationInputAssembler()
    config = SQLGenerationInputConfig(target_dialect="sqlite", max_prompt_chars=10)
    result = RenderedPromptResult(
        raw_query="list customers",
        normalized_query="list customers",
        intent_type="list",
        rendered_prompt="prompt text which is longer than 10 characters",
        rendered_sections=build_valid_rendered_sections(),
    )
    with pytest.raises(EmbeddingNonRetryableError, match="exceeds maximum limit"):
        assembler.assemble(result, config)


def test_assembler_rejects_empty_rendered_section_type():
    assembler = SQLGenerationInputAssembler()
    config = SQLGenerationInputConfig(target_dialect="sqlite")
    sections = list(build_valid_rendered_sections())
    sections[0] = RenderedPromptSection(
        section_type="",
        title="Title",
        rendered_text="text",
        source_item_ids=(),
        required=True,
    )
    result = RenderedPromptResult(
        raw_query="list customers",
        normalized_query="list customers",
        intent_type="list",
        rendered_prompt="prompt text",
        rendered_sections=tuple(sections),
    )
    with pytest.raises(EmbeddingNonRetryableError, match="Section at index 0 has empty type."):
        assembler.assemble(result, config)


def test_assembler_rejects_empty_rendered_section_title():
    assembler = SQLGenerationInputAssembler()
    config = SQLGenerationInputConfig(target_dialect="sqlite")
    sections = list(build_valid_rendered_sections())
    sections[1] = RenderedPromptSection(
        section_type="user_intent",
        title="  ",
        rendered_text="text",
        source_item_ids=(),
        required=True,
    )
    result = RenderedPromptResult(
        raw_query="list customers",
        normalized_query="list customers",
        intent_type="list",
        rendered_prompt="prompt text",
        rendered_sections=tuple(sections),
    )
    with pytest.raises(EmbeddingNonRetryableError, match="Section at index 1 has empty title."):
        assembler.assemble(result, config)


def test_assembler_rejects_empty_rendered_section_text():
    assembler = SQLGenerationInputAssembler()
    config = SQLGenerationInputConfig(target_dialect="sqlite")
    sections = list(build_valid_rendered_sections())
    sections[2] = RenderedPromptSection(
        section_type="schema_context",
        title="Schema Context",
        rendered_text="",
        source_item_ids=(),
        required=True,
    )
    result = RenderedPromptResult(
        raw_query="list customers",
        normalized_query="list customers",
        intent_type="list",
        rendered_prompt="prompt text",
        rendered_sections=tuple(sections),
    )
    with pytest.raises(EmbeddingNonRetryableError, match="Section at index 2 has empty rendered text."):
        assembler.assemble(result, config)


def test_assembler_computes_prompt_char_count():
    assembler = SQLGenerationInputAssembler()
    config = SQLGenerationInputConfig(target_dialect="sqlite")
    prompt_text = "Hello World"
    result = RenderedPromptResult(
        raw_query="list customers",
        normalized_query="list customers",
        intent_type="list",
        rendered_prompt=prompt_text,
        rendered_sections=build_valid_rendered_sections(),
    )
    assembled = assembler.assemble(result, config)
    assert assembled.prompt_char_count == len(prompt_text)


def test_assembler_computes_deterministic_prompt_sha256():
    assembler = SQLGenerationInputAssembler()
    config = SQLGenerationInputConfig(target_dialect="sqlite")
    prompt_text = "Deterministic Prompt Hashing Test"
    result = RenderedPromptResult(
        raw_query="list customers",
        normalized_query="list customers",
        intent_type="list",
        rendered_prompt=prompt_text,
        rendered_sections=build_valid_rendered_sections(),
    )
    assembled = assembler.assemble(result, config)
    expected_sha = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()
    assert assembled.prompt_sha256 == expected_sha


def test_assembler_preserves_source_section_types():
    assembler = SQLGenerationInputAssembler()
    config = SQLGenerationInputConfig(target_dialect="sqlite")
    result = RenderedPromptResult(
        raw_query="list customers",
        normalized_query="list customers",
        intent_type="list",
        rendered_prompt="prompt text",
        rendered_sections=build_valid_rendered_sections(),
    )
    assembled = assembler.assemble(result, config)
    expected_sections = (
        "system_instructions",
        "user_intent",
        "schema_context",
        "relationship_context",
        "constraints",
        "output_contract",
    )
    assert assembled.source_section_types == expected_sections


def test_assembler_flattens_source_item_ids():
    assembler = SQLGenerationInputAssembler()
    config = SQLGenerationInputConfig(target_dialect="sqlite")
    sections = list(build_valid_rendered_sections())
    sections[2] = RenderedPromptSection(
        section_type="schema_context",
        title="Schema Context",
        rendered_text="## Schema Context",
        source_item_ids=("table:customers", "column:customers.id"),
        required=True,
    )
    sections[3] = RenderedPromptSection(
        section_type="relationship_context",
        title="Relationship Context",
        rendered_text="## Relationship Context",
        source_item_ids=("relationship:orders.customer_id->customers.id",),
        required=True,
    )
    result = RenderedPromptResult(
        raw_query="list customers",
        normalized_query="list customers",
        intent_type="list",
        rendered_prompt="prompt text",
        rendered_sections=tuple(sections),
    )
    assembled = assembler.assemble(result, config)
    assert assembled.source_item_ids == (
        "table:customers",
        "column:customers.id",
        "relationship:orders.customer_id->customers.id",
    )


def test_assembler_deduplicates_source_item_ids_preserving_order():
    assembler = SQLGenerationInputAssembler()
    config = SQLGenerationInputConfig(target_dialect="sqlite")
    sections = list(build_valid_rendered_sections())
    sections[2] = RenderedPromptSection(
        section_type="schema_context",
        title="Schema Context",
        rendered_text="## Schema Context",
        source_item_ids=("table:customers", "column:customers.id", "table:customers"),
        required=True,
    )
    sections[3] = RenderedPromptSection(
        section_type="relationship_context",
        title="Relationship Context",
        rendered_text="## Relationship Context",
        source_item_ids=("column:customers.id", "relationship:orders.customer_id->customers.id"),
        required=True,
    )
    result = RenderedPromptResult(
        raw_query="list customers",
        normalized_query="list customers",
        intent_type="list",
        rendered_prompt="prompt text",
        rendered_sections=tuple(sections),
    )
    assembled = assembler.assemble(result, config)
    assert assembled.source_item_ids == (
        "table:customers",
        "column:customers.id",
        "relationship:orders.customer_id->customers.id",
    )


def test_assembler_emits_deterministic_constraints():
    assembler = SQLGenerationInputAssembler()
    config = SQLGenerationInputConfig(
        target_dialect="sqlite",
        require_sql_only_output=True,
        allow_dml=False,
        allow_ddl=False,
    )
    result = RenderedPromptResult(
        raw_query="list customers",
        normalized_query="list customers",
        intent_type="list",
        rendered_prompt="prompt text",
        rendered_sections=build_valid_rendered_sections(),
    )
    assembled = assembler.assemble(result, config)
    
    constraint_dict = {c.name: c.value for c in assembled.constraints}
    assert constraint_dict["target_dialect"] == "sqlite"
    assert constraint_dict["require_sql_only_output"] == "true"
    assert constraint_dict["allow_dml"] == "false"
    assert constraint_dict["allow_ddl"] == "false"


def test_assembler_is_deterministic_for_same_input():
    assembler = SQLGenerationInputAssembler()
    config = SQLGenerationInputConfig(target_dialect="postgresql")
    result = RenderedPromptResult(
        raw_query="list customers",
        normalized_query="list customers",
        intent_type="list",
        rendered_prompt="prompt text",
        rendered_sections=build_valid_rendered_sections(),
    )
    assembled1 = assembler.assemble(result, config)
    assembled2 = assembler.assemble(result, config)
    assert assembled1 == assembled2
