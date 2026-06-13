import pytest
from app.query_understanding.intent_context_bridge_contract import IntentContextBridgeResult, IntentBoundContextItem
from app.prompting.prompt_planner import PromptPlanner
from app.retrieval.embedding_pipeline import EmbeddingNonRetryableError


def build_mock_bridge_result(
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
    bound_items: tuple = ()
) -> IntentContextBridgeResult:
    return IntentContextBridgeResult(
        raw_query=raw_query,
        normalized_query=normalized_query,
        intent_type=intent_type,
        has_filter=has_filter,
        has_aggregation=has_aggregation,
        has_grouping=has_grouping,
        has_ordering=has_ordering,
        has_limit=has_limit,
        requires_join=requires_join,
        has_time_range=has_time_range,
        ambiguity_detected=ambiguity_detected,
        bound_items=bound_items,
        excluded_item_ids=()
    )


def build_mock_bound_item(
    id: str,
    object_type: str,
    context_role: str = "supporting_context",
    text: str = "meta details",
    binding_reason: str = "reasons"
) -> IntentBoundContextItem:
    return IntentBoundContextItem(
        id=id,
        object_id=id.split(":")[-1],
        object_type=object_type,
        text=text,
        context_role=context_role,  # type: ignore
        binding_reason=binding_reason,
        estimated_tokens=5,
        retrieval_score=0.9,
        ranking_score=0.95,
        rank=1,
        source_candidate_rank=1,
        selection_reason="matched key",
        summary_version="schema_summary_v1",
        schema_hash="fake_hash",
        provider_id="fake_provider",
        model_id="fake_model",
        dimension=128
    )


# ----------------------------------------------------
# Validation Tests
# ----------------------------------------------------

def test_planner_rejects_empty_raw_query():
    planner = PromptPlanner()
    bridge_res = build_mock_bridge_result(raw_query="")
    with pytest.raises(EmbeddingNonRetryableError, match="Raw query cannot be empty"):
        planner.plan(bridge_res)


def test_planner_rejects_empty_normalized_query():
    planner = PromptPlanner()
    bridge_res = build_mock_bridge_result(normalized_query="")
    with pytest.raises(EmbeddingNonRetryableError, match="Normalized query cannot be empty"):
        planner.plan(bridge_res)


def test_planner_rejects_empty_intent_type():
    planner = PromptPlanner()
    bridge_res = build_mock_bridge_result(intent_type="")
    with pytest.raises(EmbeddingNonRetryableError, match="Intent type cannot be empty"):
        planner.plan(bridge_res)


def test_planner_rejects_duplicate_bound_item_ids():
    planner = PromptPlanner()
    item = build_mock_bound_item("table:customers", "table")
    bridge_res = build_mock_bridge_result(bound_items=(item, item))
    with pytest.raises(EmbeddingNonRetryableError, match="Duplicate bound item ID found"):
        planner.plan(bridge_res)


def test_planner_rejects_empty_bound_item_text():
    planner = PromptPlanner()
    item = build_mock_bound_item("table:customers", "table", text="")
    bridge_res = build_mock_bridge_result(bound_items=(item,))
    with pytest.raises(EmbeddingNonRetryableError, match="has empty text"):
        planner.plan(bridge_res)


def test_planner_rejects_empty_binding_reason():
    planner = PromptPlanner()
    item = build_mock_bound_item("table:customers", "table", binding_reason="")
    bridge_res = build_mock_bridge_result(bound_items=(item,))
    with pytest.raises(EmbeddingNonRetryableError, match="has empty binding reason"):
        planner.plan(bridge_res)


def test_planner_rejects_unknown_context_role():
    planner = PromptPlanner()
    item = build_mock_bound_item("table:customers", "table", context_role="invalid_role")
    bridge_res = build_mock_bridge_result(bound_items=(item,))
    with pytest.raises(EmbeddingNonRetryableError, match="has unknown context role"):
        planner.plan(bridge_res)


# ----------------------------------------------------
# Section & Ordering Tests
# ----------------------------------------------------

def test_planner_emits_fixed_section_order():
    planner = PromptPlanner()
    bridge_res = build_mock_bridge_result()
    res = planner.plan(bridge_res)
    
    section_types = [sec.section_type for sec in res.sections]
    expected_order = [
        "system_instructions",
        "user_intent",
        "schema_context",
        "relationship_context",
        "constraints",
        "output_contract"
    ]
    assert section_types == expected_order


def test_planner_emits_all_required_sections():
    planner = PromptPlanner()
    bridge_res = build_mock_bridge_result()
    res = planner.plan(bridge_res)
    
    assert len(res.sections) == 6
    for sec in res.sections:
        assert sec.required is True
        assert len(sec.title) > 0


# ----------------------------------------------------
# Role Mapping Tests
# ----------------------------------------------------

def test_planner_maps_join_candidate_to_relationship_context():
    planner = PromptPlanner()
    item = build_mock_bound_item("relationship:customers->orders", "relationship", context_role="join_candidate")
    bridge_res = build_mock_bridge_result(bound_items=(item,))
    res = planner.plan(bridge_res)
    
    # Check relationship section contains it
    rel_section = [s for s in res.sections if s.section_type == "relationship_context"][0]
    assert len(rel_section.content_items) == 1
    assert "relationship:customers->orders" in rel_section.content_items[0]
    assert rel_section.source_item_ids == ("relationship:customers->orders",)


def test_planner_maps_primary_table_to_schema_context():
    planner = PromptPlanner()
    item = build_mock_bound_item("table:customers", "table", context_role="primary_table")
    bridge_res = build_mock_bridge_result(bound_items=(item,))
    res = planner.plan(bridge_res)
    
    schema_section = [s for s in res.sections if s.section_type == "schema_context"][0]
    assert len(schema_section.content_items) == 1
    assert "table:customers" in schema_section.content_items[0]
    assert "primary_table" in schema_section.content_items[0]


def test_planner_maps_filter_candidate_to_schema_context():
    planner = PromptPlanner()
    item = build_mock_bound_item("column:customers.id", "column", context_role="filter_candidate")
    bridge_res = build_mock_bridge_result(bound_items=(item,))
    res = planner.plan(bridge_res)
    
    schema_section = [s for s in res.sections if s.section_type == "schema_context"][0]
    assert len(schema_section.content_items) == 1
    assert "column:customers.id" in schema_section.content_items[0]
    assert "filter_candidate" in schema_section.content_items[0]


def test_planner_maps_ordering_candidate_to_schema_context():
    planner = PromptPlanner()
    item = build_mock_bound_item("column:customers.created_at", "column", context_role="ordering_candidate")
    bridge_res = build_mock_bridge_result(bound_items=(item,))
    res = planner.plan(bridge_res)
    
    schema_section = [s for s in res.sections if s.section_type == "schema_context"][0]
    assert len(schema_section.content_items) == 1
    assert "column:customers.created_at" in schema_section.content_items[0]
    assert "ordering_candidate" in schema_section.content_items[0]


def test_planner_schema_context_excludes_join_candidate():
    planner = PromptPlanner()
    item1 = build_mock_bound_item("table:customers", "table", context_role="primary_table")
    item2 = build_mock_bound_item("relationship:customers->orders", "relationship", context_role="join_candidate")
    bridge_res = build_mock_bridge_result(bound_items=(item1, item2))
    res = planner.plan(bridge_res)
    
    schema_section = [s for s in res.sections if s.section_type == "schema_context"][0]
    assert len(schema_section.content_items) == 1
    assert "table:customers" in schema_section.content_items[0]
    assert "relationship:customers->orders" not in schema_section.content_items[0]


def test_planner_relationship_context_excludes_non_join_roles():
    planner = PromptPlanner()
    item1 = build_mock_bound_item("table:customers", "table", context_role="primary_table")
    item2 = build_mock_bound_item("relationship:customers->orders", "relationship", context_role="join_candidate")
    bridge_res = build_mock_bridge_result(bound_items=(item1, item2))
    res = planner.plan(bridge_res)
    
    rel_section = [s for s in res.sections if s.section_type == "relationship_context"][0]
    assert len(rel_section.content_items) == 1
    assert "relationship:customers->orders" in rel_section.content_items[0]
    assert "table:customers" not in rel_section.content_items[0]


# ----------------------------------------------------
# Metadata & Source Tests
# ----------------------------------------------------

def test_planner_preserves_source_item_ids():
    planner = PromptPlanner()
    item = build_mock_bound_item("table:customers", "table")
    bridge_res = build_mock_bridge_result(bound_items=(item,))
    res = planner.plan(bridge_res)
    
    schema_section = [s for s in res.sections if s.section_type == "schema_context"][0]
    assert schema_section.source_item_ids == ("table:customers",)


def test_user_intent_section_contains_intent_type():
    planner = PromptPlanner()
    bridge_res = build_mock_bridge_result(intent_type="ranking")
    res = planner.plan(bridge_res)
    
    intent_sec = [s for s in res.sections if s.section_type == "user_intent"][0]
    assert any("Intent Type: ranking" in item for item in intent_sec.content_items)


def test_user_intent_section_contains_flags():
    planner = PromptPlanner()
    bridge_res = build_mock_bridge_result(has_filter=True, requires_join=True)
    res = planner.plan(bridge_res)
    
    intent_sec = [s for s in res.sections if s.section_type == "user_intent"][0]
    assert any("Filters Required: True" in item for item in intent_sec.content_items)
    assert any("Joins Required: True" in item for item in intent_sec.content_items)


def test_context_sections_include_binding_reasons():
    planner = PromptPlanner()
    item = build_mock_bound_item("table:customers", "table", binding_reason="Mocked binding description")
    bridge_res = build_mock_bridge_result(bound_items=(item,))
    res = planner.plan(bridge_res)
    
    schema_sec = [s for s in res.sections if s.section_type == "schema_context"][0]
    assert any("Reason: Mocked binding description" in item for item in schema_sec.content_items)


# ----------------------------------------------------
# Determinism Test
# ----------------------------------------------------

def test_planner_is_deterministic_for_same_input():
    planner = PromptPlanner()
    item = build_mock_bound_item("table:customers", "table")
    bridge_res = build_mock_bridge_result(bound_items=(item,))
    
    res1 = planner.plan(bridge_res)
    res2 = planner.plan(bridge_res)
    
    assert res1.sections == res2.sections
    assert res1.plan_version == res2.plan_version
