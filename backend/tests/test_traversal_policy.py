import pytest
from app.schema_graph.traversal_policy import TraversalPolicy

def test_traversal_policy_defaults():
    policy = TraversalPolicy()
    assert policy.min_candidate_score == 0.45
    assert policy.min_edge_weight == 0.50
    assert policy.max_depth == 2
    assert policy.max_neighbors_per_seed == 5
    assert policy.exclude_hubs is True
    assert policy.allow_hubs_as_connectors is False
    assert policy.token_budget == 6000
    assert policy.max_tables == 30
    assert policy.path_mode == "undirected_weighted"
