import pytest
from app.retrieval.retrieval_contract import TopKRetrievalResult, RetrievalCandidate
from app.retrieval.context_ranking_contract import ContextRankingConfig
from app.retrieval.context_ranker import DeterministicContextRanker
from app.retrieval.embedding_pipeline import EmbeddingNonRetryableError

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
        text=f"Summary of {cand_id}",
        score=score,
        rank=rank,
        summary_version="schema_summary_v1",
        schema_hash="fake_hash",
        provider_id="fake_provider",
        model_id="fake_model",
        dimension=128
    )

def test_ranker_rejects_max_candidates_zero():
    ranker = DeterministicContextRanker()
    query_result = TopKRetrievalResult(query_text="test", k_requested=5, k_returned=1, candidates=(
        build_mock_candidate("table:test", "test", "table", 0.8, 1),
    ))
    config = ContextRankingConfig(max_candidates=0)
    with pytest.raises(EmbeddingNonRetryableError, match="max_candidates must be greater than zero"):
        ranker.rank(query_result, config)

def test_ranker_rejects_negative_max_candidates():
    ranker = DeterministicContextRanker()
    query_result = TopKRetrievalResult(query_text="test", k_requested=5, k_returned=1, candidates=(
        build_mock_candidate("table:test", "test", "table", 0.8, 1),
    ))
    config = ContextRankingConfig(max_candidates=-5)
    with pytest.raises(EmbeddingNonRetryableError, match="max_candidates must be greater than zero"):
        ranker.rank(query_result, config)

def test_ranker_rejects_duplicate_candidate_ids():
    ranker = DeterministicContextRanker()
    query_result = TopKRetrievalResult(query_text="test", k_requested=5, k_returned=2, candidates=(
        build_mock_candidate("table:test", "test", "table", 0.8, 1),
        build_mock_candidate("table:test", "test", "table", 0.9, 2),
    ))
    config = ContextRankingConfig(max_candidates=5)
    with pytest.raises(EmbeddingNonRetryableError, match="Duplicate candidate ID detected"):
        ranker.rank(query_result, config)

def test_ranker_returns_empty_result_for_empty_candidates():
    ranker = DeterministicContextRanker()
    query_result = TopKRetrievalResult(query_text="test", k_requested=5, k_returned=0, candidates=())
    config = ContextRankingConfig(max_candidates=5)
    result = ranker.rank(query_result, config)
    assert len(result.items) == 0
    assert result.query_text == "test"

def test_ranker_sorts_by_ranking_score_desc():
    ranker = DeterministicContextRanker()
    
    # cand1: column, retrieval=0.9, boosted=0.9 (bonus=0)
    cand1 = build_mock_candidate("column:customers.id", "customers.id", "column", 0.9, 1)
    # cand2: table, retrieval=0.88, boosted=0.91 (bonus=0.03) -> should rank higher!
    cand2 = build_mock_candidate("table:customers", "customers", "table", 0.88, 2)
    
    query_result = TopKRetrievalResult(query_text="test", k_requested=5, k_returned=2, candidates=(cand1, cand2))
    config = ContextRankingConfig(max_candidates=5)
    
    result = ranker.rank(query_result, config)
    assert result.items[0].id == "table:customers"
    assert result.items[1].id == "column:customers.id"

def test_ranker_uses_retrieval_score_as_secondary_sort():
    ranker = DeterministicContextRanker()
    
    # All are columns, boosted = retrieval
    cand1 = build_mock_candidate("column:customers.name", "customers.name", "column", 0.8, 1)
    cand2 = build_mock_candidate("column:customers.email", "customers.email", "column", 0.85, 2)
    
    query_result = TopKRetrievalResult(query_text="test", k_requested=5, k_returned=2, candidates=(cand1, cand2))
    config = ContextRankingConfig(max_candidates=5)
    
    result = ranker.rank(query_result, config)
    assert result.items[0].id == "column:customers.email"
    assert result.items[1].id == "column:customers.name"

def test_ranker_uses_id_ascending_tie_break():
    ranker = DeterministicContextRanker()
    
    # Identical retrieval and boosted scores
    cand1 = build_mock_candidate("column:customers.name", "customers.name", "column", 0.8, 1)
    cand2 = build_mock_candidate("column:customers.email", "customers.email", "column", 0.8, 2)
    
    query_result = TopKRetrievalResult(query_text="test", k_requested=5, k_returned=2, candidates=(cand1, cand2))
    config = ContextRankingConfig(max_candidates=5)
    
    result = ranker.rank(query_result, config)
    # Alphabetical email < name
    assert result.items[0].id == "column:customers.email"
    assert result.items[1].id == "column:customers.name"

def test_ranker_applies_relationship_bonus():
    ranker = DeterministicContextRanker()
    cand = build_mock_candidate("relationship:orders.customer_id->customers.id", "orders.customer_id->customers.id", "relationship", 0.8, 1)
    
    query_result = TopKRetrievalResult(query_text="test", k_requested=5, k_returned=1, candidates=(cand,))
    config = ContextRankingConfig(max_candidates=5)
    
    result = ranker.rank(query_result, config)
    assert pytest.approx(result.items[0].ranking_score, abs=1e-6) == 0.85

def test_ranker_applies_table_bonus():
    ranker = DeterministicContextRanker()
    cand = build_mock_candidate("table:customers", "customers", "table", 0.8, 1)
    
    query_result = TopKRetrievalResult(query_text="test", k_requested=5, k_returned=1, candidates=(cand,))
    config = ContextRankingConfig(max_candidates=5)
    
    result = ranker.rank(query_result, config)
    assert pytest.approx(result.items[0].ranking_score, abs=1e-6) == 0.83

def test_ranker_filters_below_min_score():
    ranker = DeterministicContextRanker()
    
    cand1 = build_mock_candidate("table:customers", "customers", "table", 0.8, 1)
    cand2 = build_mock_candidate("column:customers.id", "customers.id", "column", 0.5, 2)
    
    query_result = TopKRetrievalResult(query_text="test", k_requested=5, k_returned=2, candidates=(cand1, cand2))
    config = ContextRankingConfig(max_candidates=5, min_score=0.6)
    
    result = ranker.rank(query_result, config)
    assert len(result.items) == 1
    assert result.items[0].id == "table:customers"

def test_ranker_limits_to_max_candidates():
    ranker = DeterministicContextRanker()
    
    cand1 = build_mock_candidate("table:customers", "customers", "table", 0.8, 1)
    cand2 = build_mock_candidate("column:customers.id", "customers.id", "column", 0.75, 2)
    cand3 = build_mock_candidate("column:customers.email", "customers.email", "column", 0.7, 3)
    
    query_result = TopKRetrievalResult(query_text="test", k_requested=5, k_returned=3, candidates=(cand1, cand2, cand3))
    config = ContextRankingConfig(max_candidates=2)
    
    result = ranker.rank(query_result, config)
    assert len(result.items) == 2
    assert result.items[0].id == "table:customers"
    assert result.items[1].id == "column:customers.id"

def test_ranker_assigns_rank_starting_from_1():
    ranker = DeterministicContextRanker()
    
    cand1 = build_mock_candidate("table:customers", "customers", "table", 0.8, 1)
    cand2 = build_mock_candidate("column:customers.id", "customers.id", "column", 0.75, 2)
    
    query_result = TopKRetrievalResult(query_text="test", k_requested=5, k_returned=2, candidates=(cand1, cand2))
    config = ContextRankingConfig(max_candidates=5)
    
    result = ranker.rank(query_result, config)
    assert result.items[0].rank == 1
    assert result.items[1].rank == 2

def test_ranker_sets_selection_reason():
    ranker = DeterministicContextRanker()
    
    cand1 = build_mock_candidate("table:customers", "customers", "table", 0.8, 1)
    cand2 = build_mock_candidate("relationship:a->b", "a->b", "relationship", 0.8, 2)
    cand3 = build_mock_candidate("column:customers.email", "customers.email", "column", 0.8, 3)
    cand4 = build_mock_candidate("column:orders", "orders", "column", 0.8, 4)
    
    query_result = TopKRetrievalResult(query_text="test", k_requested=5, k_returned=4, candidates=(cand1, cand2, cand3, cand4))
    config = ContextRankingConfig(max_candidates=5)
    
    result = ranker.rank(query_result, config)
    
    assert "Relationship matched (boosted by +0.05)" in result.items[0].selection_reason
    assert "Table matched (boosted by +0.03)" in result.items[1].selection_reason
    assert "Column matched (parent table: customers)" in result.items[2].selection_reason
    assert "Column matched (parent table: unknown)" in result.items[3].selection_reason

def test_ranker_preserves_summary_version_schema_hash_provider_model_dimension():
    ranker = DeterministicContextRanker()
    cand = RetrievalCandidate(
        id="table:customers",
        object_id="customers",
        object_type="table",
        text="text",
        score=0.8,
        rank=1,
        summary_version="schema_version_test",
        schema_hash="hash_test",
        provider_id="provider_test",
        model_id="model_test",
        dimension=128
    )
    query_result = TopKRetrievalResult(query_text="test", k_requested=5, k_returned=1, candidates=(cand,))
    config = ContextRankingConfig(max_candidates=5)
    
    result = ranker.rank(query_result, config)
    item = result.items[0]
    assert item.summary_version == "schema_version_test"
    assert item.schema_hash == "hash_test"
    assert item.provider_id == "provider_test"
    assert item.model_id == "model_test"
    assert item.dimension == 128

def test_ranker_preserves_source_candidate_rank():
    ranker = DeterministicContextRanker()
    cand = build_mock_candidate("table:customers", "customers", "table", 0.8, 9)
    
    query_result = TopKRetrievalResult(query_text="test", k_requested=10, k_returned=1, candidates=(cand,))
    config = ContextRankingConfig(max_candidates=5)
    
    result = ranker.rank(query_result, config)
    assert result.items[0].source_candidate_rank == 9
    assert result.items[0].rank == 1

def test_ranker_preserves_object_type_and_object_id():
    ranker = DeterministicContextRanker()
    cand = build_mock_candidate("table:customers", "customers", "table", 0.8, 1)
    
    query_result = TopKRetrievalResult(query_text="test", k_requested=5, k_returned=1, candidates=(cand,))
    config = ContextRankingConfig(max_candidates=5)
    
    result = ranker.rank(query_result, config)
    assert result.items[0].object_type == "table"
    assert result.items[0].object_id == "customers"
