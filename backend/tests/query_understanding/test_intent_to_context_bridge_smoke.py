from app.query_understanding.intent_extractor import DeterministicRuleBasedIntentExtractor
from app.retrieval.token_budget_contract import TokenBudgetResult, BudgetedContextItem
from app.query_understanding.intent_context_bridge import IntentContextBridge


def build_smoke_budget_item(
    id: str,
    object_type: str,
    text: str = "item text",
    estimated_tokens: int = 5,
    included: bool = True
) -> BudgetedContextItem:
    return BudgetedContextItem(
        id=id,
        object_id=id.split(":")[-1],
        object_type=object_type,
        text=text,
        estimated_tokens=estimated_tokens,
        included=included,
        exclusion_reason=None if included else "exceeds_remaining_token_budget",
        retrieval_score=0.85,
        ranking_score=0.90,
        rank=1,
        source_candidate_rank=1,
        selection_reason="matched key",
        summary_version="schema_summary_v1",
        schema_hash="hash-123",
        provider_id="provider-abc",
        model_id="model-xyz",
        dimension=128
    )


def test_intent_to_context_bridge_smoke():
    """
    E2E offline smoke test validating User Query -> IntentExtractionResult
    and TokenBudgetResult -> IntentContextBridgeResult integration.
    """
    # 1. Intent Extraction
    query = "Top 10 customers by unpaid orders last month"
    extractor = DeterministicRuleBasedIntentExtractor()
    intent_result = extractor.extract(query)
    
    # Assert query understand signals for safety
    assert intent_result.intent.intent_type == "ranking"
    assert intent_result.intent.has_filter is True
    assert intent_result.intent.has_ordering is True
    assert intent_result.intent.has_limit is True
    assert intent_result.intent.requires_join is True
    assert intent_result.intent.has_time_range is True
    assert intent_result.intent.has_grouping is False
    
    # 2. Token Budget Result
    # relationship item
    rel_item = build_smoke_budget_item("relationship:orders.customer_id->customers.id", "relationship", "orders customers link", 4)
    # table item
    tab_item = build_smoke_budget_item("table:customers", "table", "customers table details", 3)
    # column item
    col_item = build_smoke_budget_item("column:orders.status", "column", "status of orders", 3)
    
    # excluded column item
    exc_item = build_smoke_budget_item("column:customers.email", "column", "email of customers", 3, included=False)
    
    budget_result = TokenBudgetResult(
        query_text=query,
        max_total_tokens=100,
        reserved_output_tokens=10,
        effective_context_budget=90,
        used_context_tokens=10,
        included_items=(rel_item, tab_item, col_item),
        excluded_items=(exc_item,)
    )
    
    # 3. Binding Step
    bridge = IntentContextBridge()
    bridge_result = bridge.bind(intent_result, budget_result)
    
    # 4. Assertions
    assert bridge_result.bridge_version == "intent_context_bridge_v1"
    assert bridge_result.raw_query == query
    assert bridge_result.normalized_query == "top 10 customers by unpaid orders last month"
    assert bridge_result.intent_type == "ranking"
    
    # Flags preserved
    assert bridge_result.has_filter is True
    assert bridge_result.has_ordering is True
    assert bridge_result.has_limit is True
    assert bridge_result.requires_join is True
    assert bridge_result.has_time_range is True
    assert bridge_result.has_grouping is False
    
    # Included items
    assert len(bridge_result.bound_items) == 3
    
    bound_rel = bridge_result.bound_items[0]
    assert bound_rel.id == "relationship:orders.customer_id->customers.id"
    # relationship + requires_join is True -> join_candidate
    assert bound_rel.context_role == "join_candidate"
    assert len(bound_rel.binding_reason) > 0
    
    bound_tab = bridge_result.bound_items[1]
    assert bound_tab.id == "table:customers"
    # table + first table processed -> primary_table
    assert bound_tab.context_role == "primary_table"
    assert len(bound_tab.binding_reason) > 0
    
    bound_col = bridge_result.bound_items[2]
    assert bound_col.id == "column:orders.status"
    # column + has_ordering is True -> ordering_candidate (precedence ordering_candidate (4) > filter_candidate (5))
    assert bound_col.context_role == "ordering_candidate"
    assert len(bound_col.binding_reason) > 0
    
    # Excluded items
    assert bridge_result.excluded_item_ids == ("column:customers.email",)
    
    # Metadata preserved on bound items
    for item in bridge_result.bound_items:
        assert item.summary_version == "schema_summary_v1"
        assert item.schema_hash == "hash-123"
        assert item.provider_id == "provider-abc"
        assert item.model_id == "model-xyz"
        assert item.dimension == 128
        assert item.retrieval_score == 0.85
        assert item.ranking_score == 0.90
        assert item.rank == 1
        assert item.source_candidate_rank == 1
