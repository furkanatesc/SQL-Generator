import pytest
from app.retrieval.context_ranking_contract import RankedContextItem, RankedContextResult
from app.retrieval.token_budget_contract import TokenBudgetConfig
from app.retrieval.token_budget_manager import SimpleTokenEstimator, TokenBudgetManager
from app.retrieval.embedding_pipeline import EmbeddingNonRetryableError


def build_mock_ranked_item(
    id: str,
    text: str,
    ranking_score: float,
    retrieval_score: float,
    rank: int,
) -> RankedContextItem:
    return RankedContextItem(
        id=id,
        object_id=id.split(":")[-1] if ":" in id else id,
        object_type=id.split(":")[0] if ":" in id else "table",
        text=text,
        retrieval_score=retrieval_score,
        ranking_score=ranking_score,
        rank=rank,
        source_candidate_rank=rank,
        selection_reason="Mock matched",
        summary_version="v1",
        schema_hash="abc-hash",
        provider_id="mock-provider",
        model_id="mock-model",
        dimension=1536
    )


# ----------------------------------------------------
# Estimator Tests
# ----------------------------------------------------

def test_simple_token_estimator_is_deterministic():
    estimator = SimpleTokenEstimator()
    text = "hello world context items estimation"
    val1 = estimator.estimate(text)
    val2 = estimator.estimate(text)
    assert val1 == val2
    assert val1 == 7  # ceil(5 * 1.3) = ceil(6.5) = 7


def test_simple_token_estimator_rejects_empty_text():
    estimator = SimpleTokenEstimator()
    with pytest.raises(EmbeddingNonRetryableError, match="Empty text is not allowed"):
        estimator.estimate("")
    with pytest.raises(EmbeddingNonRetryableError, match="Empty text is not allowed"):
        estimator.estimate("    ")


def test_simple_token_estimator_estimates_non_empty_text():
    estimator = SimpleTokenEstimator()
    # 1 word -> ceil(1 * 1.3) = 2
    assert estimator.estimate("hello") == 2
    # 2 words -> ceil(2 * 1.3) = 3
    assert estimator.estimate("hello world") == 3


# ----------------------------------------------------
# Validation Tests
# ----------------------------------------------------

def test_token_budget_rejects_max_total_tokens_zero():
    manager = TokenBudgetManager()
    estimator = SimpleTokenEstimator()
    ranked_result = RankedContextResult(query_text="q", items=())
    config = TokenBudgetConfig(max_total_tokens=0)
    with pytest.raises(EmbeddingNonRetryableError, match="max_total_tokens must be greater than zero"):
        manager.apply_budget(ranked_result, config, estimator)


def test_token_budget_rejects_negative_max_total_tokens():
    manager = TokenBudgetManager()
    estimator = SimpleTokenEstimator()
    ranked_result = RankedContextResult(query_text="q", items=())
    config = TokenBudgetConfig(max_total_tokens=-50)
    with pytest.raises(EmbeddingNonRetryableError, match="max_total_tokens must be greater than zero"):
        manager.apply_budget(ranked_result, config, estimator)


def test_token_budget_rejects_negative_reserved_output_tokens():
    manager = TokenBudgetManager()
    estimator = SimpleTokenEstimator()
    ranked_result = RankedContextResult(query_text="q", items=())
    config = TokenBudgetConfig(max_total_tokens=100, reserved_output_tokens=-10)
    with pytest.raises(EmbeddingNonRetryableError, match="reserved_output_tokens must be non-negative"):
        manager.apply_budget(ranked_result, config, estimator)


def test_token_budget_rejects_reserved_output_tokens_equal_to_max_total_tokens():
    manager = TokenBudgetManager()
    estimator = SimpleTokenEstimator()
    ranked_result = RankedContextResult(query_text="q", items=())
    config = TokenBudgetConfig(max_total_tokens=100, reserved_output_tokens=100)
    with pytest.raises(EmbeddingNonRetryableError, match="must be less than max_total_tokens"):
        manager.apply_budget(ranked_result, config, estimator)


def test_token_budget_rejects_reserved_output_tokens_greater_than_max_total_tokens():
    manager = TokenBudgetManager()
    estimator = SimpleTokenEstimator()
    ranked_result = RankedContextResult(query_text="q", items=())
    config = TokenBudgetConfig(max_total_tokens=100, reserved_output_tokens=150)
    with pytest.raises(EmbeddingNonRetryableError, match="must be less than max_total_tokens"):
        manager.apply_budget(ranked_result, config, estimator)


def test_token_budget_rejects_unsupported_truncation_strategy():
    manager = TokenBudgetManager()
    estimator = SimpleTokenEstimator()
    ranked_result = RankedContextResult(query_text="q", items=())
    # bypass typing check for testing unsupported strategy
    config = TokenBudgetConfig(max_total_tokens=100, truncation_strategy="invalid_strategy" * 1) # type: ignore
    with pytest.raises(EmbeddingNonRetryableError, match="Unsupported truncation strategy"):
        manager.apply_budget(ranked_result, config, estimator)


# ----------------------------------------------------
# Budget Behavior Tests
# ----------------------------------------------------

def test_token_budget_includes_items_until_budget_exhausted():
    manager = TokenBudgetManager()
    estimator = SimpleTokenEstimator()
    
    items = (
        build_mock_ranked_item("table:customers", "customers metadata here", 0.95, 0.90, 1), # 3 words -> ceil(3.9) = 4 tokens
        build_mock_ranked_item("table:orders", "orders metadata description", 0.92, 0.88, 2),    # 3 words -> 4 tokens
        build_mock_ranked_item("table:payments", "payments table status", 0.85, 0.80, 3),      # 3 words -> 4 tokens
    )
    
    ranked_result = RankedContextResult(query_text="List customers", items=items)
    
    # max_total_tokens=10, reserved_output_tokens=2 -> effective budget = 8 tokens
    # customer fits (4 used)
    # orders fits (4 used, total 8)
    # payments exceeds (needs 4, only 0 remaining) -> excluded
    config = TokenBudgetConfig(max_total_tokens=10, reserved_output_tokens=2)
    
    result = manager.apply_budget(ranked_result, config, estimator)
    
    assert len(result.included_items) == 2
    assert len(result.excluded_items) == 1
    assert result.included_items[0].id == "table:customers"
    assert result.included_items[1].id == "table:orders"
    assert result.excluded_items[0].id == "table:payments"
    assert result.used_context_tokens == 8


def test_token_budget_excludes_items_that_exceed_remaining_budget():
    manager = TokenBudgetManager()
    estimator = SimpleTokenEstimator()
    
    items = (
        build_mock_ranked_item("table:customers", "customers metadata here", 0.95, 0.90, 1), # 3 words -> 4 tokens
        build_mock_ranked_item("table:orders", "orders metadata description details", 0.92, 0.88, 2), # 4 words -> ceil(5.2) = 6 tokens
        build_mock_ranked_item("table:payments", "payments info", 0.85, 0.80, 3), # 2 words -> 3 tokens
    )
    
    ranked_result = RankedContextResult(query_text="List customers", items=items)
    
    # max_total_tokens=9, reserved_output_tokens=1 -> effective budget = 8 tokens
    # customer fits (4 used)
    # orders needs 6 -> exceeds remaining budget 4 -> excluded
    # payments is not even processed / excluded since orders was excluded (prefix-based truncation)
    config = TokenBudgetConfig(max_total_tokens=9, reserved_output_tokens=1)
    
    result = manager.apply_budget(ranked_result, config, estimator)
    
    assert len(result.included_items) == 1
    assert len(result.excluded_items) == 2
    assert result.included_items[0].id == "table:customers"
    assert result.excluded_items[0].id == "table:orders"
    assert result.excluded_items[1].id == "table:payments"
    assert result.used_context_tokens == 4


def test_token_budget_preserves_ranked_order():
    manager = TokenBudgetManager()
    estimator = SimpleTokenEstimator()
    
    items = (
        build_mock_ranked_item("table:customers", "customers metadata here", 0.95, 0.90, 1),
        build_mock_ranked_item("table:orders", "orders details", 0.92, 0.88, 2),
        build_mock_ranked_item("table:payments", "payments info", 0.85, 0.80, 3),
    )
    
    ranked_result = RankedContextResult(query_text="List customers", items=items)
    config = TokenBudgetConfig(max_total_tokens=20) # fits all
    
    result = manager.apply_budget(ranked_result, config, estimator)
    
    assert [x.id for x in result.included_items] == ["table:customers", "table:orders", "table:payments"]


def test_token_budget_does_not_split_item_text():
    manager = TokenBudgetManager()
    estimator = SimpleTokenEstimator()
    
    items = (
        build_mock_ranked_item("table:customers", "customers metadata here", 0.95, 0.90, 1), # 4 tokens
    )
    
    ranked_result = RankedContextResult(query_text="q", items=items)
    config = TokenBudgetConfig(max_total_tokens=3) # effective budget 3, item needs 4
    
    result = manager.apply_budget(ranked_result, config, estimator)
    
    assert len(result.included_items) == 0
    assert len(result.excluded_items) == 1
    # Check that text is preserved completely and not sliced
    assert result.excluded_items[0].text == "customers metadata here"


def test_token_budget_used_tokens_never_exceeds_effective_budget():
    manager = TokenBudgetManager()
    estimator = SimpleTokenEstimator()
    
    items = (
        build_mock_ranked_item("table:customers", "customers", 0.95, 0.90, 1),  # 2 tokens
        build_mock_ranked_item("table:orders", "orders metadata", 0.92, 0.88, 2), # 3 tokens
    )
    
    ranked_result = RankedContextResult(query_text="q", items=items)
    config = TokenBudgetConfig(max_total_tokens=4) # effective budget = 4
    
    result = manager.apply_budget(ranked_result, config, estimator)
    assert result.used_context_tokens <= result.effective_context_budget
    assert result.used_context_tokens == 2 # orders needed 3, remaining budget was 2 -> couldn't fit.


def test_token_budget_sets_exclusion_reason_for_excluded_items():
    manager = TokenBudgetManager()
    estimator = SimpleTokenEstimator()
    
    items = (
        build_mock_ranked_item("table:customers", "customers info metadata description", 0.95, 0.90, 1), # 6 tokens
    )
    
    ranked_result = RankedContextResult(query_text="q", items=items)
    config = TokenBudgetConfig(max_total_tokens=5) # effective budget 5
    
    result = manager.apply_budget(ranked_result, config, estimator)
    assert len(result.excluded_items) == 1
    assert result.excluded_items[0].exclusion_reason == "exceeds_remaining_token_budget"


def test_token_budget_sets_no_exclusion_reason_for_included_items():
    manager = TokenBudgetManager()
    estimator = SimpleTokenEstimator()
    
    items = (
        build_mock_ranked_item("table:customers", "customers info", 0.95, 0.90, 1), # 3 tokens
    )
    
    ranked_result = RankedContextResult(query_text="q", items=items)
    config = TokenBudgetConfig(max_total_tokens=10)
    
    result = manager.apply_budget(ranked_result, config, estimator)
    assert len(result.included_items) == 1
    assert result.included_items[0].exclusion_reason is None


def test_token_budget_preserves_retrieval_and_ranking_scores():
    manager = TokenBudgetManager()
    estimator = SimpleTokenEstimator()
    
    items = (
        build_mock_ranked_item("table:customers", "customers info", 0.95, 0.90, 1),
    )
    
    ranked_result = RankedContextResult(query_text="q", items=items)
    config = TokenBudgetConfig(max_total_tokens=10)
    
    result = manager.apply_budget(ranked_result, config, estimator)
    item = result.included_items[0]
    assert item.ranking_score == 0.95
    assert item.retrieval_score == 0.90


def test_token_budget_preserves_summary_metadata():
    manager = TokenBudgetManager()
    estimator = SimpleTokenEstimator()
    
    items = (
        build_mock_ranked_item("table:customers", "customers info", 0.95, 0.90, 1),
    )
    
    ranked_result = RankedContextResult(query_text="q", items=items)
    config = TokenBudgetConfig(max_total_tokens=10)
    
    result = manager.apply_budget(ranked_result, config, estimator)
    item = result.included_items[0]
    assert item.summary_version == "v1"
    assert item.schema_hash == "abc-hash"
    assert item.provider_id == "mock-provider"
    assert item.model_id == "mock-model"
    assert item.dimension == 1536
