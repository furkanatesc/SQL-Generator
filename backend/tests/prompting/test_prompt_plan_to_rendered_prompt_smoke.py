from app.query_understanding.intent_context_bridge_contract import IntentContextBridgeResult, IntentBoundContextItem
from app.prompting.prompt_planner import PromptPlanner
from app.prompting.prompt_renderer import PromptRenderer
from app.prompting.prompt_render_contract import PROMPT_RENDER_VERSION


def build_smoke_bound_item(
    id: str,
    object_type: str,
    context_role: str,
    text: str,
    binding_reason: str
) -> IntentBoundContextItem:
    return IntentBoundContextItem(
        id=id,
        object_id=id.split(":")[-1],
        object_type=object_type,
        text=text,
        context_role=context_role,  # type: ignore
        binding_reason=binding_reason,
        estimated_tokens=4,
        retrieval_score=0.88,
        ranking_score=0.91,
        rank=1,
        source_candidate_rank=1,
        selection_reason="matched",
        summary_version="schema_summary_v1",
        schema_hash="hash-123",
        provider_id="provider-abc",
        model_id="model-xyz",
        dimension=128
    )


def test_prompt_plan_to_rendered_prompt_smoke_flow():
    """
    E2E offline smoke test validating IntentContextBridgeResult -> PromptPlanResult -> RenderedPromptResult flow.
    Asserts deterministic section sequencing, flag inclusion, and final markdown bullet format.
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

    # 3. Assertions
    assert rendered_result.prompt_render_version == PROMPT_RENDER_VERSION
    assert rendered_result.raw_query == query
    assert rendered_result.normalized_query == "top 10 customers by unpaid orders last month"
    assert rendered_result.intent_type == "ranking"

    # Verify structured sections exist in sequence
    assert len(rendered_result.rendered_sections) == 6
    expected_types = [
        "system_instructions",
        "user_intent",
        "schema_context",
        "relationship_context",
        "constraints",
        "output_contract"
    ]
    actual_types = [sec.section_type for sec in rendered_result.rendered_sections]
    assert actual_types == expected_types

    # Verify formatting (Headers and bullet lists)
    rendered_prompt = rendered_result.rendered_prompt

    # Header check
    assert "## System Instructions" in rendered_prompt
    assert "## User Intent" in rendered_prompt
    assert "## Schema Context" in rendered_prompt
    assert "## Relationship Context" in rendered_prompt
    assert "## Constraints" in rendered_prompt
    assert "## Output Contract" in rendered_prompt

    # Content checks for lists
    # System instructions list check
    assert "- You are a SQL generation planner." in rendered_prompt
    assert "- Use only provided schema context." in rendered_prompt
    assert "- Do not invent tables or columns." in rendered_prompt
    
    # User Intent check
    assert "- Intent Type: ranking" in rendered_prompt
    assert "- Filters Required: True" in rendered_prompt
    assert "- Ordering Required: True" in rendered_prompt
    assert "- Limit Required: True" in rendered_prompt
    assert "- Joins Required: True" in rendered_prompt

    # Schema Context check
    assert "- Table/Column: table:customers | Role: primary_table | Reason: first table processed | Text: customers info table" in rendered_prompt
    assert "- Table/Column: column:orders.status | Role: ordering_candidate | Reason: has ordering signal | Text: status column" in rendered_prompt

    # Relationship Context check
    assert "- Relationship: relationship:orders.customer_id->customers.id | Reason: requires join | Text: link orders to customers" in rendered_prompt

    # Constraints check
    assert "- Use only listed tables and columns." in rendered_prompt
    assert "- Prefer explicit joins from relationship context." in rendered_prompt

    # Output Contract check
    assert "- Expected output: SQL string only." in rendered_prompt
    assert "- No markdown." in rendered_prompt
    assert "- No explanation." in rendered_prompt

    # Double check that sections are joined by double newlines
    joined_expected = "\n\n".join(sec.rendered_text for sec in rendered_result.rendered_sections)
    assert rendered_prompt == joined_expected
