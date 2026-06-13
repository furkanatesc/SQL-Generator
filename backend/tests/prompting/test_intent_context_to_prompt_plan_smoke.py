from app.query_understanding.intent_context_bridge_contract import IntentContextBridgeResult, IntentBoundContextItem
from app.prompting.prompt_planner import PromptPlanner


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


def test_intent_context_to_prompt_plan_smoke():
    """
    E2E offline smoke test validating IntentContextBridgeResult -> PromptPlanResult flow.
    Asserts deterministic section sequencing, flag inclusion, and context grouping.
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
    
    # 2. Planning Step
    planner = PromptPlanner()
    plan_result = planner.plan(bridge_result)
    
    # 3. Assertions
    assert plan_result.plan_version == "prompt_plan_v1"
    assert plan_result.raw_query == query
    assert plan_result.normalized_query == "top 10 customers by unpaid orders last month"
    assert plan_result.intent_type == "ranking"
    
    # Verify deterministic section order
    section_types = [sec.section_type for sec in plan_result.sections]
    expected_order = [
        "system_instructions",
        "user_intent",
        "schema_context",
        "relationship_context",
        "constraints",
        "output_contract"
    ]
    assert section_types == expected_order
    
    # User Intent Section Check
    intent_sec = plan_result.sections[1]
    assert intent_sec.section_type == "user_intent"
    assert any("Intent Type: ranking" in item for item in intent_sec.content_items)
    assert any("Filters Required: True" in item for item in intent_sec.content_items)
    assert any("Ordering Required: True" in item for item in intent_sec.content_items)
    assert any("Limit Required: True" in item for item in intent_sec.content_items)
    assert any("Joins Required: True" in item for item in intent_sec.content_items)
    assert any("Grouping Required: False" in item for item in intent_sec.content_items)

    # Schema Context Section Check (excludes relationship: join_candidate)
    schema_sec = plan_result.sections[2]
    assert schema_sec.section_type == "schema_context"
    assert schema_sec.source_item_ids == ("table:customers", "column:orders.status")
    assert any("table:customers" in item for item in schema_sec.content_items)
    assert any("column:orders.status" in item for item in schema_sec.content_items)
    assert any("primary_table" in item for item in schema_sec.content_items)
    assert any("ordering_candidate" in item for item in schema_sec.content_items)

    # Relationship Context Section Check (only join_candidate)
    rel_sec = plan_result.sections[3]
    assert rel_sec.section_type == "relationship_context"
    assert rel_sec.source_item_ids == ("relationship:orders.customer_id->customers.id",)
    assert any("relationship:orders.customer_id->customers.id" in item for item in rel_sec.content_items)

    # Constraints Section Check
    constraints_sec = plan_result.sections[4]
    assert constraints_sec.section_type == "constraints"
    assert any("Use only listed tables and columns." in item for item in constraints_sec.content_items)

    # Output Contract Section Check
    output_sec = plan_result.sections[5]
    assert output_sec.section_type == "output_contract"
    assert any("Expected output: SQL string only." in item for item in output_sec.content_items)
