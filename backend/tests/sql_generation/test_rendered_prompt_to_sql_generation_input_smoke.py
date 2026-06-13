import hashlib
from app.prompting.prompt_render_contract import RenderedPromptResult, RenderedPromptSection, PROMPT_RENDER_VERSION
from app.sql_generation.sql_generation_input_contract import (
    SQLGenerationInputConfig,
    SQL_GENERATION_INPUT_VERSION,
)
from app.sql_generation.sql_generation_input_assembler import SQLGenerationInputAssembler


def test_rendered_prompt_to_sql_generation_input_smoke_flow():
    """
    E2E offline smoke test validating RenderedPromptResult -> SQLGenerationInputResult flow.
    """
    raw_query = "List customers with unpaid orders"
    normalized_query = "list customers with unpaid orders"
    intent_type = "list"

    sections = (
        RenderedPromptSection(
            section_type="system_instructions",
            title="System Instructions",
            rendered_text="## System Instructions\n- You are a precise and helpful Text-to-SQL assistant.",
            source_item_ids=(),
            required=True
        ),
        RenderedPromptSection(
            section_type="user_intent",
            title="User Intent",
            rendered_text="## User Intent\n- Intent Type: list",
            source_item_ids=(),
            required=True
        ),
        RenderedPromptSection(
            section_type="schema_context",
            title="Schema Context",
            rendered_text="## Schema Context\n- Table/Column: table:customers | Role: primary_table",
            source_item_ids=("table:customers", "column:customers.id"),
            required=True
        ),
        RenderedPromptSection(
            section_type="relationship_context",
            title="Relationship Context",
            rendered_text="## Relationship Context\n- Relationship: relationship:orders.customer_id->customers.id",
            source_item_ids=("relationship:orders.customer_id->customers.id",),
            required=True
        ),
        RenderedPromptSection(
            section_type="constraints",
            title="Constraints",
            rendered_text="## Constraints\n- Use only listed tables and columns.",
            source_item_ids=(),
            required=True
        ),
        RenderedPromptSection(
            section_type="output_contract",
            title="Output Contract",
            rendered_text="## Output Contract\n- Expected output: SQL string only.",
            source_item_ids=(),
            required=True
        ),
    )

    rendered_prompt = "\n\n".join(sec.rendered_text for sec in sections)

    rendered_result = RenderedPromptResult(
        raw_query=raw_query,
        normalized_query=normalized_query,
        intent_type=intent_type,
        rendered_prompt=rendered_prompt,
        rendered_sections=sections,
        prompt_render_version=PROMPT_RENDER_VERSION
    )

    config = SQLGenerationInputConfig(
        target_dialect="sqlite",
        max_prompt_chars=10000,
        require_sql_only_output=True,
        allow_dml=False,
        allow_ddl=False,
    )

    assembler = SQLGenerationInputAssembler()
    assembled_result = assembler.assemble(rendered_result, config)

    # Assertions
    assert assembled_result.input_version == SQL_GENERATION_INPUT_VERSION
    assert assembled_result.raw_query == raw_query
    assert assembled_result.normalized_query == normalized_query
    assert assembled_result.intent_type == intent_type
    assert assembled_result.target_dialect == "sqlite"
    assert assembled_result.rendered_prompt == rendered_prompt
    assert assembled_result.prompt_char_count == len(rendered_prompt)

    expected_sha = hashlib.sha256(rendered_prompt.encode("utf-8")).hexdigest()
    assert assembled_result.prompt_sha256 == expected_sha

    # Verify flattened section types
    assert assembled_result.source_section_types == (
        "system_instructions",
        "user_intent",
        "schema_context",
        "relationship_context",
        "constraints",
        "output_contract",
    )

    # Verify flattened and deduplicated source item ids
    assert assembled_result.source_item_ids == (
        "table:customers",
        "column:customers.id",
        "relationship:orders.customer_id->customers.id",
    )

    # Verify deterministic constraints list
    expected_constraints = {
        "target_dialect": "sqlite",
        "require_sql_only_output": "true",
        "allow_dml": "false",
        "allow_ddl": "false"
    }
    actual_constraints = {c.name: c.value for c in assembled_result.constraints}
    assert actual_constraints == expected_constraints
