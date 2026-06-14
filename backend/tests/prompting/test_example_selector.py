import pytest
import hashlib
import socket
from app.query_understanding.intent_context_bridge_contract import IntentContextBridgeResult
from app.prompting.few_shot_contract import SQLFewShotExample, SQLFewShotExampleSet
from app.prompting.example_selection_contract import (
    SQLExampleSelectionConfig,
    SQLExampleSelectionResult,
    SQLExampleSelectionContractError,
    SQL_EXAMPLE_SELECTION_VERSION
)
from app.prompting.example_selector import SQLExampleSelector


def build_dummy_bridge_result(
    intent_type: str = "selection",
    requires_join: bool = False,
    has_aggregation: bool = False,
    has_grouping: bool = False,
    has_ordering: bool = False,
    has_limit: bool = False,
    has_time_range: bool = False
) -> IntentContextBridgeResult:
    return IntentContextBridgeResult(
        raw_query="SELECT 1",
        normalized_query="select 1",
        intent_type=intent_type,
        has_filter=False,
        has_aggregation=has_aggregation,
        has_grouping=has_grouping,
        has_ordering=has_ordering,
        has_limit=has_limit,
        requires_join=requires_join,
        has_time_range=has_time_range,
        ambiguity_detected=False,
        bound_items=(),
        excluded_item_ids=()
    )


def build_dummy_example(
    id: str,
    dialect: str = "sqlite",
    intent_type: str = "selection",
    tags: tuple = ()
) -> SQLFewShotExample:
    return SQLFewShotExample(
        id=id,
        dialect=dialect,
        intent_type=intent_type,
        question="Dummy question?",
        schema_context=("tbl1",),
        sql="SELECT 1",
        notes=(),
        tags=tags
    )


def test_selector_rejects_unsupported_dialect():
    selector = SQLExampleSelector()
    bridge = build_dummy_bridge_result()
    ex = build_dummy_example("ex1")
    ex_set = SQLFewShotExampleSet(examples=(ex,))
    
    with pytest.raises(SQLExampleSelectionContractError) as exc_info:
        SQLExampleSelectionConfig(target_dialect="mysql")
    assert "Unsupported target dialect: 'mysql'" in str(exc_info.value)


def test_selector_rejects_empty_examples_when_required():
    selector = SQLExampleSelector()
    bridge = build_dummy_bridge_result()
    ex_set = SQLFewShotExampleSet(examples=())
    config = SQLExampleSelectionConfig(target_dialect="sqlite", required=True)

    with pytest.raises(SQLExampleSelectionContractError) as exc_info:
        selector.select_examples(bridge, ex_set, config)
    assert "Example set is empty but selection is configured as required" in str(exc_info.value)


def test_selector_allows_empty_examples_when_not_required():
    selector = SQLExampleSelector()
    bridge = build_dummy_bridge_result(intent_type="ranking")
    ex_set = SQLFewShotExampleSet(examples=())
    config = SQLExampleSelectionConfig(target_dialect="sqlite", required=False)

    res = selector.select_examples(bridge, ex_set, config)
    assert res.selected_examples == ()
    assert res.selected_example_ids == ()
    assert res.rejected_example_ids == ()
    assert res.selection_reasons == ()
    assert res.intent_type == "ranking"
    assert res.version == SQL_EXAMPLE_SELECTION_VERSION


def test_selector_filters_by_dialect():
    selector = SQLExampleSelector()
    bridge = build_dummy_bridge_result()
    ex1 = build_dummy_example("ex_sqlite", dialect="sqlite")
    ex2 = build_dummy_example("ex_postgres", dialect="postgresql")
    ex_set = SQLFewShotExampleSet(examples=(ex1, ex2))
    config = SQLExampleSelectionConfig(target_dialect="sqlite")

    res = selector.select_examples(bridge, ex_set, config)
    assert res.selected_example_ids == ("ex_sqlite",)
    assert res.rejected_example_ids == ("ex_postgres",)


def test_selector_respects_max_examples():
    selector = SQLExampleSelector()
    bridge = build_dummy_bridge_result()
    ex1 = build_dummy_example("ex1")
    ex2 = build_dummy_example("ex2")
    ex3 = build_dummy_example("ex3")
    ex_set = SQLFewShotExampleSet(examples=(ex1, ex2, ex3))
    config = SQLExampleSelectionConfig(target_dialect="sqlite", max_examples=2)

    res = selector.select_examples(bridge, ex_set, config)
    assert len(res.selected_examples) == 2
    assert len(res.rejected_example_ids) == 1


def test_selector_prefers_intent_type_match():
    selector = SQLExampleSelector()
    # Target intent is ranking
    bridge = build_dummy_bridge_result(intent_type="ranking")
    # ex1 matches intent ranking, ex2 is selection
    ex1 = build_dummy_example("ex_ranking", intent_type="ranking")
    ex2 = build_dummy_example("ex_selection", intent_type="selection")
    ex_set = SQLFewShotExampleSet(examples=(ex1, ex2))
    config = SQLExampleSelectionConfig(target_dialect="sqlite")

    res = selector.select_examples(bridge, ex_set, config)
    # The matching intent ex_ranking must be selected first
    assert res.selected_example_ids[0] == "ex_ranking"


def test_selector_scores_join_signal():
    selector = SQLExampleSelector()
    bridge = build_dummy_bridge_result(requires_join=True)
    # ex1 tag contains 'join', ex2 does not
    ex1 = build_dummy_example("ex_join", tags=("join",))
    ex2 = build_dummy_example("ex_no_join", tags=())
    ex_set = SQLFewShotExampleSet(examples=(ex1, ex2))
    config = SQLExampleSelectionConfig(target_dialect="sqlite")

    res = selector.select_examples(bridge, ex_set, config)
    assert res.selected_example_ids[0] == "ex_join"
    reason = next(r for r in res.selection_reasons if r.example_id == "ex_join")
    assert "join_match" in reason.matched_signals
    # score must be 100 (for intent mismatch as it defaults to selection) + 20 (join_match) = 120
    # Wait, in dummy example, ex_join intent_type is 'selection', bridge intent_type is 'selection'.
    # So intent matches (100) + join match (20) = 120.
    assert reason.score == 120


def test_selector_scores_aggregation_signal():
    selector = SQLExampleSelector()
    bridge = build_dummy_bridge_result(has_aggregation=True)
    ex1 = build_dummy_example("ex_agg", tags=("aggregation",))
    ex2 = build_dummy_example("ex_no_agg")
    ex_set = SQLFewShotExampleSet(examples=(ex1, ex2))
    config = SQLExampleSelectionConfig(target_dialect="sqlite")

    res = selector.select_examples(bridge, ex_set, config)
    assert res.selected_example_ids[0] == "ex_agg"
    reason = next(r for r in res.selection_reasons if r.example_id == "ex_agg")
    assert "aggregation_match" in reason.matched_signals
    assert reason.score == 120


def test_selector_scores_ordering_limit_signals():
    selector = SQLExampleSelector()
    bridge = build_dummy_bridge_result(has_ordering=True, has_limit=True)
    ex1 = build_dummy_example("ex_ord_lim", tags=("ordering", "limit"))
    ex2 = build_dummy_example("ex_none")
    ex_set = SQLFewShotExampleSet(examples=(ex1, ex2))
    config = SQLExampleSelectionConfig(target_dialect="sqlite")

    res = selector.select_examples(bridge, ex_set, config)
    assert res.selected_example_ids[0] == "ex_ord_lim"
    reason = next(r for r in res.selection_reasons if r.example_id == "ex_ord_lim")
    assert "ordering_match" in reason.matched_signals
    assert "limit_match" in reason.matched_signals
    # 100 (intent) + 10 (ordering) + 10 (limit) = 120
    assert reason.score == 120


def test_selector_uses_deterministic_tie_break_by_example_id():
    selector = SQLExampleSelector()
    bridge = build_dummy_bridge_result()
    # Both have score 100 (intent match, no special signals)
    ex1 = build_dummy_example("ex_b")
    ex2 = build_dummy_example("ex_a")
    ex_set = SQLFewShotExampleSet(examples=(ex1, ex2))
    config = SQLExampleSelectionConfig(target_dialect="sqlite", max_examples=1)

    res = selector.select_examples(bridge, ex_set, config)
    # Tie break should choose ex_a because "ex_a" < "ex_b" alphabetically
    assert res.selected_example_ids == ("ex_a",)
    assert res.rejected_example_ids == ("ex_b",)


def test_selector_returns_selection_reasons_for_selected_examples():
    selector = SQLExampleSelector()
    bridge = build_dummy_bridge_result(requires_join=True)
    ex = build_dummy_example("ex_join", tags=("join",))
    ex_set = SQLFewShotExampleSet(examples=(ex,))
    config = SQLExampleSelectionConfig(target_dialect="sqlite")

    res = selector.select_examples(bridge, ex_set, config)
    assert len(res.selection_reasons) == 1
    assert res.selection_reasons[0].example_id == "ex_join"
    assert res.selection_reasons[0].score == 120
    assert "join_match" in res.selection_reasons[0].matched_signals


def test_selector_returns_rejected_example_ids():
    selector = SQLExampleSelector()
    bridge = build_dummy_bridge_result()
    ex1 = build_dummy_example("ex1", dialect="sqlite")
    ex2 = build_dummy_example("ex2", dialect="postgresql")  # Mismatched dialect
    ex3 = build_dummy_example("ex3", dialect="sqlite")      # Mismatched score limit
    ex_set = SQLFewShotExampleSet(examples=(ex1, ex2, ex3))
    config = SQLExampleSelectionConfig(target_dialect="sqlite", max_examples=1)

    res = selector.select_examples(bridge, ex_set, config)
    # ex2 is dialect mismatch, ex3 is over budget
    # rejected_example_ids must track both
    assert "ex2" in res.rejected_example_ids
    assert "ex3" in res.rejected_example_ids


def test_selector_computes_selection_fingerprint():
    selector = SQLExampleSelector()
    bridge = build_dummy_bridge_result()
    ex = build_dummy_example("ex1")
    ex_set = SQLFewShotExampleSet(examples=(ex,))
    config = SQLExampleSelectionConfig(target_dialect="sqlite")

    res = selector.select_examples(bridge, ex_set, config)
    assert len(res.selection_fingerprint) == 64
    
    # Verify fingerprint matches expected deterministic SHA-256 calculation
    sorted_ids = "ex1"
    raw_str = (
        f"dialect:sqlite|max:3|req:True|intent:selection|join:False|agg:False|"
        f"grp:False|ord:False|lim:False|time:False|candidates:{sorted_ids}"
    )
    expected_sha = hashlib.sha256(raw_str.encode("utf-8")).hexdigest()
    assert res.selection_fingerprint == expected_sha


def test_selector_is_deterministic_for_same_input():
    selector = SQLExampleSelector()
    bridge1 = build_dummy_bridge_result(intent_type="ranking", requires_join=True)
    bridge2 = build_dummy_bridge_result(intent_type="ranking", requires_join=True)
    
    ex1 = build_dummy_example("ex1", tags=("join",))
    ex2 = build_dummy_example("ex2")
    ex_set1 = SQLFewShotExampleSet(examples=(ex1, ex2))
    ex_set2 = SQLFewShotExampleSet(examples=(ex1, ex2))
    
    config1 = SQLExampleSelectionConfig(target_dialect="sqlite")
    config2 = SQLExampleSelectionConfig(target_dialect="sqlite")

    res1 = selector.select_examples(bridge1, ex_set1, config1)
    res2 = selector.select_examples(bridge2, ex_set2, config2)

    assert res1.selected_example_ids == res2.selected_example_ids
    assert res1.rejected_example_ids == res2.rejected_example_ids
    assert res1.selection_reasons == res2.selection_reasons
    assert res1.selection_fingerprint == res2.selection_fingerprint


def test_selector_does_not_call_provider_or_network(monkeypatch):
    # Guard network connections
    def block_connect(*args, **kwargs):
        raise RuntimeError("Network/provider call attempted!")
    monkeypatch.setattr(socket.socket, "connect", block_connect)

    selector = SQLExampleSelector()
    bridge = build_dummy_bridge_result()
    ex = build_dummy_example("ex1")
    ex_set = SQLFewShotExampleSet(examples=(ex,))
    config = SQLExampleSelectionConfig(target_dialect="sqlite")

    res = selector.select_examples(bridge, ex_set, config)
    assert res is not None
