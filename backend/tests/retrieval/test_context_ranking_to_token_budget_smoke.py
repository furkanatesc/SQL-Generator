import pytest
from app.retrieval.retrieval_contract import TopKRetrievalResult, RetrievalCandidate
from app.retrieval.context_ranking_contract import ContextRankingConfig
from app.retrieval.context_ranker import DeterministicContextRanker
from app.retrieval.token_budget_contract import TokenBudgetConfig
from app.retrieval.token_budget_manager import SimpleTokenEstimator, TokenBudgetManager


def build_mock_candidate(
    cand_id: str,
    object_id: str,
    object_type: str,
    score: float,
    rank: int,
    text: str | None = None
) -> RetrievalCandidate:
    return RetrievalCandidate(
        id=cand_id,
        object_id=object_id,
        object_type=object_type,
        text=text or f"Summary text of {cand_id}",
        score=score,
        rank=rank,
        summary_version="schema_summary_v1",
        schema_hash="fake_hash_123",
        provider_id="fake_provider_id",
        model_id="fake_model_id",
        dimension=128
    )


def test_context_ranking_to_token_budget_smoke():
    """
    E2E offline smoke test validating TopKRetrievalResult -> RankedContextResult -> TokenBudgetResult flow.
    Asserts deterministic order preservation, used token limits, metadata preservation, and exclusion reasons.
    """
    # 1. Ranking Stage
    ranker = DeterministicContextRanker()
    cand_col = build_mock_candidate("column:orders.status", "orders.status", "column", 0.90, 1, "status column") # 2 words -> 3 tokens
    cand_rel = build_mock_candidate("relationship:orders.customer_id->customers.id", "orders.customer_id->customers.id", "relationship", 0.86, 2, "orders customers link") # 3 words -> 4 tokens
    cand_tab = build_mock_candidate("table:customers", "customers", "table", 0.87, 3, "customers details") # 2 words -> 3 tokens
    
    # Boosted:
    # relationship: 0.86 + 0.05 = 0.91 (rank 1)
    # column: 0.90 + 0.00 = 0.90 (rank 2)
    # table: 0.87 + 0.03 = 0.90 (rank 3) (since column has smaller ID lexicographically)

    retrieval_result = TopKRetrievalResult(
        query_text="unpaid orders link",
        k_requested=5,
        k_returned=3,
        candidates=(cand_col, cand_rel, cand_tab)
    )
    
    ranking_config = ContextRankingConfig(max_candidates=5)
    ranked_result = ranker.rank(retrieval_result, ranking_config)
    
    # 2. Token Budgeting Stage
    budget_manager = TokenBudgetManager()
    estimator = SimpleTokenEstimator()
    
    # Let's set max_total_tokens=10, reserved_output_tokens=2 -> effective budget = 8
    # Rank 1: relationship (needs 4 tokens) -> fits (used=4)
    # Rank 2: column (needs 3 tokens) -> fits (used=7)
    # Rank 3: table (needs 3 tokens) -> 7 + 3 = 10 > 8 -> exceeds remaining budget 1 -> excluded
    budget_config = TokenBudgetConfig(max_total_tokens=10, reserved_output_tokens=2)
    budget_result = budget_manager.apply_budget(ranked_result, budget_config, estimator)
    
    # 3. Assertions
    assert budget_result.token_budget_version == "token_budget_v1"
    assert budget_result.max_total_tokens == 10
    assert budget_result.reserved_output_tokens == 2
    assert budget_result.effective_context_budget == 8
    assert budget_result.used_context_tokens == 7
    
    # Verify order preservation & selection splits
    assert len(budget_result.included_items) == 2
    assert len(budget_result.excluded_items) == 1
    
    # Included items
    inc1 = budget_result.included_items[0]
    assert inc1.id == "relationship:orders.customer_id->customers.id"
    assert inc1.included is True
    assert inc1.exclusion_reason is None
    assert inc1.estimated_tokens == 4
    assert inc1.rank == 1
    assert inc1.source_candidate_rank == 2
    
    inc2 = budget_result.included_items[1]
    assert inc2.id == "column:orders.status"
    assert inc2.included is True
    assert inc2.exclusion_reason is None
    assert inc2.estimated_tokens == 3
    assert inc2.rank == 2
    assert inc2.source_candidate_rank == 1
    
    # Excluded items
    exc1 = budget_result.excluded_items[0]
    assert exc1.id == "table:customers"
    assert exc1.included is False
    assert exc1.exclusion_reason == "exceeds_remaining_token_budget"
    assert exc1.estimated_tokens == 3
    assert exc1.rank == 3
    assert exc1.source_candidate_rank == 3
    
    # Verify metadata preservation on both
    for item in list(budget_result.included_items) + list(budget_result.excluded_items):
        assert item.summary_version == "schema_summary_v1"
        assert item.schema_hash == "fake_hash_123"
        assert item.provider_id == "fake_provider_id"
        assert item.model_id == "fake_model_id"
        assert item.dimension == 128
