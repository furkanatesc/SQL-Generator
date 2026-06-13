from app.retrieval.retrieval_contract import TopKRetrievalResult, RetrievalCandidate
from app.retrieval.context_ranking_contract import ContextRankingConfig
from app.retrieval.context_ranker import DeterministicContextRanker

def build_mock_candidate(
    cand_id: str,
    object_id: str,
    object_type: str,
    score: float,
    rank: int
) -> RetrievalCandidate:
    return RetrievalCandidate(
        id=cand_id,
        object_id=object_id,
        object_type=object_type,
        text=f"Summary text of {cand_id}",
        score=score,
        rank=rank,
        summary_version="schema_summary_v1",
        schema_hash="fake_hash_123",
        provider_id="fake_provider_id",
        model_id="fake_model_id",
        dimension=128
    )

def test_top_k_retrieval_to_context_ranking_smoke():
    """
    E2E offline smoke test validating TopKRetrievalResult to RankedContextResult mapping
    via DeterministicContextRanker. Asserts deterministic ordering, metadata preservation,
    and selection reasons without network activity.
    """
    ranker = DeterministicContextRanker()
    
    # Generate candidates with different scores & types
    cand_col = build_mock_candidate("column:orders.status", "orders.status", "column", 0.90, 1)
    cand_rel = build_mock_candidate("relationship:orders.customer_id->customers.id", "orders.customer_id->customers.id", "relationship", 0.86, 2)
    cand_tab = build_mock_candidate("table:customers", "customers", "table", 0.87, 3)
    
    # Expected boosted scores:
    # column: 0.90 + 0.00 = 0.90
    # relationship: 0.86 + 0.05 = 0.91 -> should be first!
    # table: 0.87 + 0.03 = 0.90 -> should be tied with column, sorted by score (0.90 vs 0.90), then ID table:customers vs column:orders.status.
    # Alphabetically, "column:orders.status" < "table:customers".
    # So sorting order:
    # 1. relationship (0.91)
    # 2. column (0.90)
    # 3. table (0.90)
    
    result = TopKRetrievalResult(
        query_text="List customers with unpaid orders",
        k_requested=5,
        k_returned=3,
        candidates=(cand_col, cand_rel, cand_tab)
    )
    
    config = ContextRankingConfig(max_candidates=5)
    
    ranked_result = ranker.rank(result, config)
    
    # Assert result structure and version
    assert ranked_result.query_text == "List customers with unpaid orders"
    assert ranked_result.context_ranking_version == "context_ranking_v1"
    assert len(ranked_result.items) == 3
    
    # Assert deterministic order and scores
    item1 = ranked_result.items[0]
    assert item1.id == "relationship:orders.customer_id->customers.id"
    assert item1.rank == 1
    assert item1.source_candidate_rank == 2
    assert item1.ranking_score == 0.91
    assert "Relationship matched" in item1.selection_reason
    
    item2 = ranked_result.items[1]
    assert item2.id == "column:orders.status"
    assert item2.rank == 2
    assert item2.source_candidate_rank == 1
    assert item2.ranking_score == 0.90
    assert "Column matched (parent table: orders)" in item2.selection_reason
    
    item3 = ranked_result.items[2]
    assert item3.id == "table:customers"
    assert item3.rank == 3
    assert item3.source_candidate_rank == 3
    assert item3.ranking_score == 0.90
    assert "Table matched" in item3.selection_reason
    
    # Assert metadata preservation
    for item in ranked_result.items:
        assert item.summary_version == "schema_summary_v1"
        assert item.schema_hash == "fake_hash_123"
        assert item.provider_id == "fake_provider_id"
        assert item.model_id == "fake_model_id"
        assert item.dimension == 128
