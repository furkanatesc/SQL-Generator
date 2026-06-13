import pytest
from app.query_understanding.intent_contract import IntentExtractionResult, QueryIntent
from app.retrieval.token_budget_contract import TokenBudgetResult, BudgetedContextItem
from app.query_understanding.intent_context_bridge import IntentContextBridge
from app.retrieval.embedding_pipeline import EmbeddingNonRetryableError


def build_mock_intent_result(
    raw_query: str = "list customers",
    normalized_query: str = "list customers",
    intent_type: str = "list",
    has_filter: bool = False,
    has_aggregation: bool = False,
    has_grouping: bool = False,
    has_ordering: bool = False,
    has_limit: bool = False,
    requires_join: bool = False,
    has_time_range: bool = False,
    ambiguity_detected: bool = False,
) -> IntentExtractionResult:
    intent = QueryIntent(
        normalized_query=normalized_query,
        intent_type=intent_type,  # type: ignore
        has_filter=has_filter,
        has_aggregation=has_aggregation,
        has_grouping=has_grouping,
        has_ordering=has_ordering,
        has_limit=has_limit,
        requires_join=requires_join,
        has_time_range=has_time_range,
        ambiguity_detected=ambiguity_detected,
        signals=()
    )
    return IntentExtractionResult(raw_query=raw_query, intent=intent)


def build_mock_budget_item(
    id: str,
    object_type: str,
    text: str = "description text",
    estimated_tokens: int = 5,
) -> BudgetedContextItem:
    return BudgetedContextItem(
        id=id,
        object_id=id.split(":")[-1],
        object_type=object_type,
        text=text,
        estimated_tokens=estimated_tokens,
        included=True,
        exclusion_reason=None,
        retrieval_score=0.9,
        ranking_score=0.92,
        rank=1,
        source_candidate_rank=1,
        selection_reason="matched key",
        summary_version="schema_summary_v1",
        schema_hash="fake_hash",
        provider_id="fake_provider",
        model_id="fake_model",
        dimension=128
    )


def build_mock_budget_result(
    query_text: str = "list customers",
    included_items: tuple = (),
    excluded_items: tuple = ()
) -> TokenBudgetResult:
    return TokenBudgetResult(
        query_text=query_text,
        max_total_tokens=100,
        reserved_output_tokens=10,
        effective_context_budget=90,
        used_context_tokens=10,
        included_items=included_items,
        excluded_items=excluded_items
    )


# ----------------------------------------------------
# Validation Tests
# ----------------------------------------------------

def test_bridge_rejects_query_mismatch():
    bridge = IntentContextBridge()
    intent_res = build_mock_intent_result(raw_query="list customers")
    budget_res = build_mock_budget_result(query_text="list orders")
    with pytest.raises(EmbeddingNonRetryableError, match="Query mismatch"):
        bridge.bind(intent_res, budget_res)


def test_bridge_rejects_empty_raw_query():
    bridge = IntentContextBridge()
    intent_res = build_mock_intent_result(raw_query="")
    budget_res = build_mock_budget_result(query_text="")
    with pytest.raises(EmbeddingNonRetryableError, match="Intent raw query cannot be empty"):
        bridge.bind(intent_res, budget_res)


def test_bridge_rejects_empty_normalized_query():
    bridge = IntentContextBridge()
    intent_res = build_mock_intent_result(raw_query="q", normalized_query="")
    budget_res = build_mock_budget_result(query_text="q")
    with pytest.raises(EmbeddingNonRetryableError, match="Intent normalized query cannot be empty"):
        bridge.bind(intent_res, budget_res)


def test_bridge_rejects_empty_token_budget_query_text():
    bridge = IntentContextBridge()
    intent_res = build_mock_intent_result(raw_query="q")
    budget_res = build_mock_budget_result(query_text="")
    with pytest.raises(EmbeddingNonRetryableError, match="Token budget query text cannot be empty"):
        bridge.bind(intent_res, budget_res)


def test_bridge_rejects_duplicate_included_item_ids():
    bridge = IntentContextBridge()
    intent_res = build_mock_intent_result()
    item = build_mock_budget_item("table:customers", "table")
    budget_res = build_mock_budget_result(included_items=(item, item))
    with pytest.raises(EmbeddingNonRetryableError, match="Duplicate included item ID found"):
        bridge.bind(intent_res, budget_res)


def test_bridge_rejects_empty_item_text():
    bridge = IntentContextBridge()
    intent_res = build_mock_intent_result()
    item = build_mock_budget_item("table:customers", "table", text="")
    budget_res = build_mock_budget_result(included_items=(item,))
    with pytest.raises(EmbeddingNonRetryableError, match="has empty text"):
        bridge.bind(intent_res, budget_res)


def test_bridge_rejects_non_positive_estimated_tokens():
    bridge = IntentContextBridge()
    intent_res = build_mock_intent_result()
    item = build_mock_budget_item("table:customers", "table", estimated_tokens=0)
    budget_res = build_mock_budget_result(included_items=(item,))
    with pytest.raises(EmbeddingNonRetryableError, match="has invalid estimated tokens"):
        bridge.bind(intent_res, budget_res)


# ----------------------------------------------------
# Role Assignment & Precedence Tests
# ----------------------------------------------------

def test_bridge_assigns_join_candidate_for_relationship_when_requires_join():
    bridge = IntentContextBridge()
    intent_res = build_mock_intent_result(requires_join=True)
    item = build_mock_budget_item("relationship:customers->orders", "relationship")
    budget_res = build_mock_budget_result(included_items=(item,))
    res = bridge.bind(intent_res, budget_res)
    assert res.bound_items[0].context_role == "join_candidate"


def test_bridge_assigns_filter_candidate_when_has_filter():
    bridge = IntentContextBridge()
    intent_res = build_mock_intent_result(has_filter=True)
    item = build_mock_budget_item("column:customers.status", "column")
    budget_res = build_mock_budget_result(included_items=(item,))
    res = bridge.bind(intent_res, budget_res)
    assert res.bound_items[0].context_role == "filter_candidate"


def test_bridge_assigns_ordering_candidate_when_has_ordering():
    bridge = IntentContextBridge()
    intent_res = build_mock_intent_result(has_ordering=True)
    item = build_mock_budget_item("column:customers.created_at", "column")
    budget_res = build_mock_budget_result(included_items=(item,))
    res = bridge.bind(intent_res, budget_res)
    assert res.bound_items[0].context_role == "ordering_candidate"


def test_bridge_assigns_aggregation_candidate_when_has_aggregation():
    bridge = IntentContextBridge()
    intent_res = build_mock_intent_result(has_aggregation=True)
    item = build_mock_budget_item("column:orders.amount", "column")
    budget_res = build_mock_budget_result(included_items=(item,))
    res = bridge.bind(intent_res, budget_res)
    assert res.bound_items[0].context_role == "aggregation_candidate"


def test_bridge_assigns_grouping_candidate_when_has_grouping():
    bridge = IntentContextBridge()
    intent_res = build_mock_intent_result(has_grouping=True)
    item = build_mock_budget_item("column:orders.category", "column")
    budget_res = build_mock_budget_result(included_items=(item,))
    res = bridge.bind(intent_res, budget_res)
    assert res.bound_items[0].context_role == "grouping_candidate"


def test_bridge_assigns_primary_table_for_first_table():
    bridge = IntentContextBridge()
    intent_res = build_mock_intent_result()
    item1 = build_mock_budget_item("table:customers", "table")
    item2 = build_mock_budget_item("table:orders", "table")
    budget_res = build_mock_budget_result(included_items=(item1, item2))
    res = bridge.bind(intent_res, budget_res)
    assert res.bound_items[0].context_role == "primary_table"
    assert res.bound_items[1].context_role == "supporting_context"


def test_bridge_assigns_supporting_context_for_remaining_items():
    bridge = IntentContextBridge()
    intent_res = build_mock_intent_result()
    # table is primary table
    item1 = build_mock_budget_item("table:customers", "table")
    # column without filter/ordering/aggregation/grouping flags -> supporting_context
    item2 = build_mock_budget_item("column:customers.name", "column")
    budget_res = build_mock_budget_result(included_items=(item1, item2))
    res = bridge.bind(intent_res, budget_res)
    assert res.bound_items[0].context_role == "primary_table"
    assert res.bound_items[1].context_role == "supporting_context"


def test_bridge_role_precedence_is_deterministic():
    bridge = IntentContextBridge()
    # Query has both has_aggregation and has_ordering
    intent_res = build_mock_intent_result(has_aggregation=True, has_ordering=True)
    item = build_mock_budget_item("column:orders.amount", "column")
    budget_res = build_mock_budget_result(included_items=(item,))
    
    # Precedence says aggregation_candidate (2) > ordering_candidate (4)
    res = bridge.bind(intent_res, budget_res)
    assert res.bound_items[0].context_role == "aggregation_candidate"


# ----------------------------------------------------
# Metadata Preservation Tests
# ----------------------------------------------------

def test_bridge_preserves_scores_and_ranks():
    bridge = IntentContextBridge()
    intent_res = build_mock_intent_result()
    item = build_mock_budget_item("table:customers", "table")
    budget_res = build_mock_budget_result(included_items=(item,))
    res = bridge.bind(intent_res, budget_res)
    
    bound = res.bound_items[0]
    assert bound.retrieval_score == 0.9
    assert bound.ranking_score == 0.92
    assert bound.rank == 1
    assert bound.source_candidate_rank == 1


def test_bridge_preserves_selection_reason():
    bridge = IntentContextBridge()
    intent_res = build_mock_intent_result()
    item = build_mock_budget_item("table:customers", "table")
    budget_res = build_mock_budget_result(included_items=(item,))
    res = bridge.bind(intent_res, budget_res)
    assert res.bound_items[0].selection_reason == "matched key"


def test_bridge_preserves_summary_metadata():
    bridge = IntentContextBridge()
    intent_res = build_mock_intent_result()
    item = build_mock_budget_item("table:customers", "table")
    budget_res = build_mock_budget_result(included_items=(item,))
    res = bridge.bind(intent_res, budget_res)
    
    bound = res.bound_items[0]
    assert bound.summary_version == "schema_summary_v1"
    assert bound.schema_hash == "fake_hash"
    assert bound.provider_id == "fake_provider"
    assert bound.model_id == "fake_model"
    assert bound.dimension == 128


def test_bridge_preserves_estimated_tokens():
    bridge = IntentContextBridge()
    intent_res = build_mock_intent_result()
    item = build_mock_budget_item("table:customers", "table", estimated_tokens=15)
    budget_res = build_mock_budget_result(included_items=(item,))
    res = bridge.bind(intent_res, budget_res)
    assert res.bound_items[0].estimated_tokens == 15


def test_bridge_sets_non_empty_binding_reason():
    bridge = IntentContextBridge()
    intent_res = build_mock_intent_result(has_filter=True)
    item = build_mock_budget_item("column:customers.id", "column")
    budget_res = build_mock_budget_result(included_items=(item,))
    res = bridge.bind(intent_res, budget_res)
    assert len(res.bound_items[0].binding_reason) > 0
