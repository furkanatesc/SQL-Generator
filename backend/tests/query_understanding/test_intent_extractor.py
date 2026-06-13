import pytest
from app.query_understanding.intent_extractor import DeterministicRuleBasedIntentExtractor
from app.retrieval.embedding_pipeline import EmbeddingNonRetryableError


# ----------------------------------------------------
# Normalization Tests
# ----------------------------------------------------

def test_normalize_query_trims_whitespace():
    extractor = DeterministicRuleBasedIntentExtractor()
    result = extractor.extract("   list customers   ")
    assert result.intent.normalized_query == "list customers"


def test_normalize_query_collapses_multiple_spaces():
    extractor = DeterministicRuleBasedIntentExtractor()
    result = extractor.extract("list     customers   with   orders")
    assert result.intent.normalized_query == "list customers with orders"


def test_normalize_query_lowercases_text():
    extractor = DeterministicRuleBasedIntentExtractor()
    result = extractor.extract("List Customers With Orders")
    assert result.intent.normalized_query == "list customers with orders"


def test_normalize_query_is_deterministic():
    extractor = DeterministicRuleBasedIntentExtractor()
    q = "  List   Customers  "
    r1 = extractor.extract(q)
    r2 = extractor.extract(q)
    assert r1.intent.normalized_query == r2.intent.normalized_query
    assert r1.intent.intent_type == r2.intent.intent_type


# ----------------------------------------------------
# Validation Tests
# ----------------------------------------------------

def test_extractor_rejects_empty_query():
    extractor = DeterministicRuleBasedIntentExtractor()
    with pytest.raises(EmbeddingNonRetryableError, match="Query cannot be"):
        extractor.extract("")
    with pytest.raises(EmbeddingNonRetryableError, match="Query cannot be"):
        extractor.extract(None)  # type: ignore


def test_extractor_rejects_whitespace_only_query():
    extractor = DeterministicRuleBasedIntentExtractor()
    with pytest.raises(EmbeddingNonRetryableError, match="Query cannot be empty or whitespace-only"):
        extractor.extract("      ")


def test_extractor_rejects_query_over_max_length():
    extractor = DeterministicRuleBasedIntentExtractor(max_query_chars=10)
    with pytest.raises(EmbeddingNonRetryableError, match="exceeds maximum allowed length"):
        extractor.extract("this is a very long query")


# ----------------------------------------------------
# Intent Classification & Signal Tests
# ----------------------------------------------------

def test_extractor_detects_list_intent():
    extractor = DeterministicRuleBasedIntentExtractor()
    for kw in ["list", "show", "get", "find", "display"]:
        result = extractor.extract(f"{kw} customers")
        assert result.intent.intent_type == "list"


def test_extractor_detects_count_intent():
    extractor = DeterministicRuleBasedIntentExtractor()
    for kw in ["count", "how many", "number of"]:
        result = extractor.extract(f"{kw} payments")
        assert result.intent.intent_type == "count"


def test_extractor_detects_aggregate_intent():
    extractor = DeterministicRuleBasedIntentExtractor()
    for kw in ["sum", "total", "average", "avg", "min", "max"]:
        result = extractor.extract(f"{kw} order amount")
        assert result.intent.intent_type == "aggregate"


def test_extractor_detects_ranking_intent():
    extractor = DeterministicRuleBasedIntentExtractor()
    for kw in ["top", "highest", "lowest", "most", "least", "best", "worst"]:
        result = extractor.extract(f"{kw} customers by revenue")
        assert result.intent.intent_type == "ranking"


def test_extractor_ranking_intent_implies_ordering_signal():
    extractor = DeterministicRuleBasedIntentExtractor()
    for kw in ["top", "highest", "lowest", "most", "least", "best", "worst"]:
        result = extractor.extract(f"{kw} customers")
        assert result.intent.has_ordering is True


def test_extractor_count_sets_has_aggregation_true():
    extractor = DeterministicRuleBasedIntentExtractor()
    for kw in ["count", "how many", "number of"]:
        result = extractor.extract(f"{kw} customers")
        assert result.intent.has_aggregation is True


def test_extractor_detects_filter_signal():
    extractor = DeterministicRuleBasedIntentExtractor()
    # "unpaid" is a filter keyword
    result = extractor.extract("list orders with unpaid status")
    assert result.intent.has_filter is True
    
    # query without filter
    result_none = extractor.extract("list orders")
    assert result_none.intent.has_filter is False


def test_extractor_detects_grouping_signal():
    extractor = DeterministicRuleBasedIntentExtractor()
    # has_aggregation is True (total), by customer -> matches
    result = extractor.extract("total sales by customer")
    assert result.intent.has_grouping is True


def test_extractor_does_not_treat_ranking_by_as_grouping():
    extractor = DeterministicRuleBasedIntentExtractor()
    # ranking context (no aggregate keyword) -> has_grouping is False
    result = extractor.extract("top 10 customers by revenue")
    assert result.intent.has_grouping is False


def test_extractor_detects_grouping_for_aggregate_by_entity():
    extractor = DeterministicRuleBasedIntentExtractor()
    # "sum" is aggregate keyword, "by customer" is grouping pattern -> has_grouping is True
    result = extractor.extract("sum sales by customer")
    assert result.intent.has_grouping is True


def test_extractor_detects_grouping_for_group_by():
    extractor = DeterministicRuleBasedIntentExtractor()
    # "group by" explicitly exists -> has_grouping is True
    result = extractor.extract("list customers group by country")
    assert result.intent.has_grouping is True


def test_extractor_detects_grouping_for_per_entity():
    extractor = DeterministicRuleBasedIntentExtractor()
    # "per customer" exists -> has_grouping is True
    result = extractor.extract("sales amount per customer")
    assert result.intent.has_grouping is True


def test_extractor_detects_ordering_signal():
    extractor = DeterministicRuleBasedIntentExtractor()
    result = extractor.extract("list orders sorted by date")
    assert result.intent.has_ordering is True


def test_extractor_detects_limit_signal():
    extractor = DeterministicRuleBasedIntentExtractor()
    # matches limit patterns (keyword + number)
    assert extractor.extract("top 10 customers").intent.has_limit is True
    assert extractor.extract("first 5 orders").intent.has_limit is True
    assert extractor.extract("last 20 payments").intent.has_limit is True
    assert extractor.extract("limit 100 users").intent.has_limit is True
    
    # does not match if no number follows
    assert extractor.extract("top customers").intent.has_limit is False


def test_extractor_detects_time_range_signal():
    extractor = DeterministicRuleBasedIntentExtractor()
    result = extractor.extract("list payments since yesterday")
    assert result.intent.has_time_range is True


def test_extractor_detects_requires_join_signal():
    extractor = DeterministicRuleBasedIntentExtractor()
    # Explicit join phrase
    assert extractor.extract("list customers and their orders").intent.requires_join is True
    
    # Connector + multiple entities (customers, orders)
    assert extractor.extract("orders by customers").intent.requires_join is True
    
    # Connector but only one entity (orders) -> False
    assert extractor.extract("orders by status").intent.requires_join is False


def test_extractor_returns_unknown_for_unrecognized_query():
    extractor = DeterministicRuleBasedIntentExtractor()
    result = extractor.extract("hello from the other side")
    assert result.intent.intent_type == "unknown"


# ----------------------------------------------------
# Trace Tests
# ----------------------------------------------------

def test_true_signals_have_non_empty_reason():
    extractor = DeterministicRuleBasedIntentExtractor()
    result = extractor.extract("list orders sorted by date since yesterday")
    for sig in result.intent.signals:
        if sig.value is True:
            assert len(sig.reason) > 0


def test_false_signals_are_represented_consistently():
    extractor = DeterministicRuleBasedIntentExtractor()
    result = extractor.extract("list orders")
    for sig in result.intent.signals:
        if sig.value is False:
            assert sig.reason == ""


def test_signal_names_are_stable():
    extractor = DeterministicRuleBasedIntentExtractor()
    result = extractor.extract("list orders")
    signal_names = [sig.name for sig in result.intent.signals]
    expected_names = [
        "has_filter",
        "has_aggregation",
        "has_grouping",
        "has_ordering",
        "has_limit",
        "has_time_range",
        "requires_join",
        "ambiguity_detected"
    ]
    assert sorted(signal_names) == sorted(expected_names)
