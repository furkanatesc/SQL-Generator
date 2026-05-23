import pytest
from app.schema_graph.token_budget import TokenBudgetEstimator

def test_estimate_table_cost():
    estimator = TokenBudgetEstimator()
    meta = {
        "columns": [{}, {}, {}],  # 3 columns * 3 = 9
        "foreign_keys": [{}, {}]  # 2 FKs * 4 = 8
    }
    # base 8 + 9 + 8 = 25
    cost = estimator.estimate_table_cost("T1", meta)
    assert cost == 25

def test_can_add():
    estimator = TokenBudgetEstimator()
    assert estimator.can_add(5000, 500, 6000) is True
    assert estimator.can_add(5800, 500, 6000) is False
