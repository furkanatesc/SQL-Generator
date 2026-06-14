from app.query_understanding.intent_context_bridge_contract import IntentContextBridgeResult
from app.prompting.prompt_planner import PromptPlanner
from app.prompting.prompt_renderer import PromptRenderer
from app.sql_generation.sql_generation_input_contract import SQLGenerationInputConfig
from app.sql_generation.sql_generation_input_assembler import SQLGenerationInputAssembler
from app.prompting.sql_prompt_builder_contract import (
    SQLPromptBuilderConfig,
    SQLPromptBuilderResult,
    SQL_PROMPT_BUILDER_VERSION
)
from app.prompting.sql_prompt_builder import SQLPromptBuilder
from tests.prompting.test_prompt_plan_to_rendered_prompt_smoke import build_smoke_bound_item


def test_sql_generation_input_to_prompt_builder_v2_smoke():
    """
    E2E integration smoke test verifying the flow:
    IntentContextBridgeResult -> PromptPlanner -> PromptRenderer -> SQLGenerationInputAssembler
    -> SQLPromptBuilder -> SQLPromptBuilderResult.
    """
    query = "Top 10 customers by unpaid orders last month"

    # relationship bound item
    bound_rel = build_smoke_bound_item(
        id="relationship:orders.customer_id->customers.id",
        object_type="relationship",
        context_role="join_candidate",
        text="link orders to customers",
        binding_reason="requires join"
    )
    # table bound item
    bound_tab = build_smoke_bound_item(
        id="table:customers",
        object_type="table",
        context_role="primary_table",
        text="customers info table",
        binding_reason="first table processed"
    )
    # column bound item
    bound_col = build_smoke_bound_item(
        id="column:orders.status",
        object_type="column",
        context_role="ordering_candidate",
        text="status column",
        binding_reason="has ordering signal"
    )

    bridge_result = IntentContextBridgeResult(
        raw_query=query,
        normalized_query="top 10 customers by unpaid orders last month",
        intent_type="ranking",
        has_filter=True,
        has_aggregation=False,
        has_grouping=False,
        has_ordering=True,
        has_limit=True,
        requires_join=True,
        has_time_range=True,
        ambiguity_detected=False,
        bound_items=(bound_rel, bound_tab, bound_col),
        excluded_item_ids=("column:customers.email",)
    )

    # 1. Planning Step
    planner = PromptPlanner()
    plan_result = planner.plan(bridge_result)

    # 2. Rendering Step
    renderer = PromptRenderer()
    rendered_result = renderer.render(plan_result)

    # 3. Assemble Input Step (V1 Input Result)
    input_config = SQLGenerationInputConfig(
        target_dialect="sqlite",
        max_prompt_chars=40000,
        require_sql_only_output=True,
        allow_dml=False,
        allow_ddl=False
    )
    assembler = SQLGenerationInputAssembler()
    input_result = assembler.assemble(rendered_result, input_config)

    # 4. Prompt Builder V2 Step
    builder_config = SQLPromptBuilderConfig(
        target_dialect="sqlite",
        max_prompt_chars=30000,
        require_sql_only_output=True,
        allow_dml=False,
        allow_ddl=False
    )
    builder = SQLPromptBuilder()
    builder_result = builder.build(input_result, builder_config)

    # 5. Assertions
    assert builder_result.version == SQL_PROMPT_BUILDER_VERSION
    assert builder_result.target_dialect == "sqlite"
    assert builder_result.prompt_char_count == len(builder_result.prompt_text)
    
    # Check section existence and ordering
    expected_sections = (
        "system_rules",
        "dialect_rules",
        "schema_context",
        "relationship_context",
        "user_intent",
        "generation_constraints",
        "output_contract"
    )
    assert builder_result.section_types == expected_sections

    # Check Output Contract has sql_only instruction appended
    output_contract_sec = next(
        s for s in builder_result.sections if s.section_type == "output_contract"
    )
    sql_only_instruction = "Return only SQL. No markdown. No explanation."
    assert sql_only_instruction in output_contract_sec.content_items

    # Verify order-preserving deduplication of source_item_ids
    # The original source_item_ids in input_result are flattened from sections.
    # In V2 we deduplicate them keeping insertion order.
    flat_ids = []
    for sec in rendered_result.rendered_sections:
        flat_ids.extend(sec.source_item_ids)
    expected_deduped_ids = tuple(dict.fromkeys(flat_ids))
    assert builder_result.source_item_ids == expected_deduped_ids
