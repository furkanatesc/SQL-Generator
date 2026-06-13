import dataclasses
import pytest
from app.query_understanding.intent_context_bridge_contract import (
    INTENT_CONTEXT_BRIDGE_VERSION,
    IntentBoundContextItem,
    IntentContextBridgeResult
)


def test_intent_context_bridge_version_is_v1():
    assert INTENT_CONTEXT_BRIDGE_VERSION == "intent_context_bridge_v1"


def test_intent_bound_context_item_is_frozen():
    item = IntentBoundContextItem(
        id="table:customers",
        object_id="customers",
        object_type="table",
        text="text",
        context_role="primary_table",
        binding_reason="reason",
        estimated_tokens=5,
        retrieval_score=0.9,
        ranking_score=0.95,
        rank=1,
        source_candidate_rank=1,
        selection_reason="Table matched",
        summary_version="v1",
        schema_hash="hash",
        provider_id="provider",
        model_id="model",
        dimension=128
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        item.context_role = "join_candidate"  # type: ignore


def test_intent_context_bridge_result_is_frozen():
    result = IntentContextBridgeResult(
        raw_query="query",
        normalized_query="query",
        intent_type="list",
        has_filter=False,
        has_aggregation=False,
        has_grouping=False,
        has_ordering=False,
        has_limit=False,
        requires_join=False,
        has_time_range=False,
        ambiguity_detected=False,
        bound_items=(),
        excluded_item_ids=()
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.intent_type = "ranking"  # type: ignore


def test_bound_items_are_tuple_based():
    result = IntentContextBridgeResult(
        raw_query="query",
        normalized_query="query",
        intent_type="list",
        has_filter=False,
        has_aggregation=False,
        has_grouping=False,
        has_ordering=False,
        has_limit=False,
        requires_join=False,
        has_time_range=False,
        ambiguity_detected=False,
        bound_items=(),
        excluded_item_ids=()
    )
    assert isinstance(result.bound_items, tuple)


def test_excluded_item_ids_are_tuple_based():
    result = IntentContextBridgeResult(
        raw_query="query",
        normalized_query="query",
        intent_type="list",
        has_filter=False,
        has_aggregation=False,
        has_grouping=False,
        has_ordering=False,
        has_limit=False,
        requires_join=False,
        has_time_range=False,
        ambiguity_detected=False,
        bound_items=(),
        excluded_item_ids=()
    )
    assert isinstance(result.excluded_item_ids, tuple)
