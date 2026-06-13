from app.query_understanding.intent_extractor import DeterministicRuleBasedIntentExtractor


def test_user_query_to_intent_extraction_smoke():
    """
    E2E offline smoke test validating user query to IntentExtractionResult flow
    using a complex query containing diverse intent signals.
    """
    extractor = DeterministicRuleBasedIntentExtractor()
    query = "Top 10 customers by unpaid orders last month"
    
    result = extractor.extract(query)
    
    # 1. Basic Assertions
    assert result.raw_query == query
    assert result.extraction_version == "intent_extraction_v1"
    
    # 2. Intent Classification
    # "Top" is a ranking keyword, so intent_type should be "ranking"
    assert result.intent.intent_type == "ranking"
    
    # 3. Intent Signals
    # has_filter: True because of "unpaid"
    assert result.intent.has_filter is True
    
    # has_aggregation: False because no explicit aggregate keyword (sum, total, avg, count, min, max) is present
    assert result.intent.has_aggregation is False
    
    # has_grouping: True because of "by"
    assert result.intent.has_grouping is True
    
    # has_ordering: False because no explicit ordering keywords (order by, sort by, highest, lowest, etc.) are present
    assert result.intent.has_ordering is False
    
    # has_limit: True because of "Top 10" pattern
    assert result.intent.has_limit is True
    
    # has_time_range: True because of "last month"
    assert result.intent.has_time_range is True
    
    # requires_join: True because it contains connector "by" and two entity terms: "customers" and "orders"
    assert result.intent.requires_join is True
    
    # ambiguity_detected: False because no ambiguity keywords (some, any, maybe, etc.) are present
    assert result.intent.ambiguity_detected is False

    # 4. Verify signals trace reasons
    sig_map = {sig.name: sig for sig in result.intent.signals}
    
    assert sig_map["has_filter"].value is True
    assert "unpaid" in sig_map["has_filter"].reason
    
    assert sig_map["has_limit"].value is True
    assert "top 10" in sig_map["has_limit"].reason
    
    assert sig_map["has_time_range"].value is True
    assert "last month" in sig_map["has_time_range"].reason
    
    assert sig_map["requires_join"].value is True
    assert "customers" in sig_map["requires_join"].reason
    assert "orders" in sig_map["requires_join"].reason
