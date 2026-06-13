import dataclasses
import pytest
from app.query_understanding.intent_contract import (
    INTENT_EXTRACTION_VERSION,
    IntentSignal,
    QueryIntent,
    IntentExtractionResult
)


def test_intent_extraction_version_is_intent_extraction_v1():
    assert INTENT_EXTRACTION_VERSION == "intent_extraction_v1"


def test_query_intent_is_frozen():
    intent = QueryIntent(
        normalized_query="test",
        intent_type="list",
        has_filter=False,
        has_aggregation=False,
        has_grouping=False,
        has_ordering=False,
        has_limit=False,
        requires_join=False,
        has_time_range=False,
        ambiguity_detected=False,
        signals=()
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        intent.intent_type = "ranking"  # type: ignore


def test_intent_extraction_result_preserves_raw_query():
    intent = QueryIntent(
        normalized_query="test query",
        intent_type="list",
        has_filter=False,
        has_aggregation=False,
        has_grouping=False,
        has_ordering=False,
        has_limit=False,
        requires_join=False,
        has_time_range=False,
        ambiguity_detected=False,
        signals=()
    )
    result = IntentExtractionResult(
        raw_query="  Test Query  ",
        intent=intent
    )
    assert result.raw_query == "  Test Query  "
    assert result.intent.normalized_query == "test query"
    
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.raw_query = "new"  # type: ignore


def test_intent_signals_are_tuple_based():
    signal = IntentSignal(name="sig", value=True, reason="Reason")
    intent = QueryIntent(
        normalized_query="test",
        intent_type="list",
        has_filter=False,
        has_aggregation=False,
        has_grouping=False,
        has_ordering=False,
        has_limit=False,
        requires_join=False,
        has_time_range=False,
        ambiguity_detected=False,
        signals=(signal,)
    )
    assert isinstance(intent.signals, tuple)
    assert intent.signals[0].name == "sig"
    assert intent.signals[0].value is True
    assert intent.signals[0].reason == "Reason"
