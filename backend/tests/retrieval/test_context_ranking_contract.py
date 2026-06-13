from app.retrieval.context_ranking_contract import (
    CONTEXT_RANKING_VERSION,
    RankedContextItem,
    RankedContextResult
)

def test_context_ranking_version_is_context_ranking_v1():
    assert CONTEXT_RANKING_VERSION == "context_ranking_v1"

def test_ranked_context_item_preserves_metadata():
    item = RankedContextItem(
        id="table:customers",
        object_id="customers",
        object_type="table",
        text="table details",
        retrieval_score=0.8,
        ranking_score=0.83,
        rank=1,
        selection_reason="matched",
        source_candidate_rank=2,
        summary_version="schema_summary_v1",
        schema_hash="hash123",
        provider_id="provider_a",
        model_id="model_b",
        dimension=128
    )
    assert item.id == "table:customers"
    assert item.retrieval_score == 0.8
    assert item.ranking_score == 0.83
    assert item.summary_version == "schema_summary_v1"
    assert item.schema_hash == "hash123"
    assert item.provider_id == "provider_a"
    assert item.model_id == "model_b"
    assert item.dimension == 128

def test_ranked_context_result_is_tuple_based():
    item1 = RankedContextItem(
        id="table:customers",
        object_id="customers",
        object_type="table",
        text="table details",
        retrieval_score=0.8,
        ranking_score=0.83,
        rank=1,
        selection_reason="matched",
        source_candidate_rank=2,
        summary_version="schema_summary_v1",
        schema_hash="hash123",
        provider_id="provider_a",
        model_id="model_b",
        dimension=128
    )
    
    result = RankedContextResult(
        query_text="List customers",
        items=(item1,)
    )
    
    assert isinstance(result.items, tuple)
    assert result.context_ranking_version == "context_ranking_v1"
