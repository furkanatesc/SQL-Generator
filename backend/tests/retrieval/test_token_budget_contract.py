import dataclasses
import pytest
from app.retrieval.token_budget_contract import (
    TOKEN_BUDGET_VERSION,
    TokenBudgetConfig,
    BudgetedContextItem,
    TokenBudgetResult
)


def test_token_budget_version_is_token_budget_v1():
    assert TOKEN_BUDGET_VERSION == "token_budget_v1"


def test_token_budget_config_is_frozen():
    config = TokenBudgetConfig(max_total_tokens=100)
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.max_total_tokens = 200  # type: ignore


def test_budgeted_context_item_preserves_metadata():
    item = BudgetedContextItem(
        id="table:customers",
        object_id="customers",
        object_type="table",
        text="table customers description",
        estimated_tokens=5,
        included=True,
        exclusion_reason=None,
        retrieval_score=0.9,
        ranking_score=0.95,
        rank=1,
        source_candidate_rank=1,
        selection_reason="Table matched",
        summary_version="v1",
        schema_hash="abc",
        provider_id="fake",
        model_id="fake-model",
        dimension=1536
    )
    
    assert item.id == "table:customers"
    assert item.object_id == "customers"
    assert item.object_type == "table"
    assert item.text == "table customers description"
    assert item.estimated_tokens == 5
    assert item.included is True
    assert item.exclusion_reason is None
    assert item.retrieval_score == 0.9
    assert item.ranking_score == 0.95
    assert item.rank == 1
    assert item.source_candidate_rank == 1
    assert item.selection_reason == "Table matched"
    assert item.summary_version == "v1"
    assert item.schema_hash == "abc"
    assert item.provider_id == "fake"
    assert item.model_id == "fake-model"
    assert item.dimension == 1536

    with pytest.raises(dataclasses.FrozenInstanceError):
        item.included = False  # type: ignore


def test_token_budget_result_is_tuple_based():
    item = BudgetedContextItem(
        id="table:customers",
        object_id="customers",
        object_type="table",
        text="table customers description",
        estimated_tokens=5,
        included=True,
        exclusion_reason=None,
        retrieval_score=0.9,
        ranking_score=0.95,
        rank=1,
        source_candidate_rank=1,
        selection_reason="Table matched",
        summary_version="v1",
        schema_hash="abc",
        provider_id="fake",
        model_id="fake-model",
        dimension=1536
    )
    
    result = TokenBudgetResult(
        query_text="List customers",
        max_total_tokens=100,
        reserved_output_tokens=10,
        effective_context_budget=90,
        used_context_tokens=5,
        included_items=(item,),
        excluded_items=()
    )
    
    assert isinstance(result.included_items, tuple)
    assert isinstance(result.excluded_items, tuple)
    assert result.token_budget_version == "token_budget_v1"

    with pytest.raises(dataclasses.FrozenInstanceError):
        result.used_context_tokens = 10  # type: ignore
