import pytest
from unittest.mock import MagicMock

from app.schema_graph.graph_pruner import GraphPruner
from app.schema_graph.traversal_policy import TraversalPolicy
from app.schema_graph.token_budget import TokenBudgetEstimator
from app.schema_graph.hub_detector import HubDetector
from app.schema_graph.networkx_backend import NetworkXGraphBackend
from app.nlp.text_normalizer import TextNormalizer
from app.schema_candidates import CandidateAggregate, CandidateSignal
from app.schema_pruner import SchemaPruner


@pytest.fixture
def pruner_dependencies():
    normalizer = TextNormalizer()
    graph_backend = NetworkXGraphBackend()
    budget_estimator = TokenBudgetEstimator()
    hub_detector = HubDetector(normalizer=normalizer)
    
    pruner = GraphPruner(
        graph_backend=graph_backend,
        budget_estimator=budget_estimator,
        hub_detector=hub_detector,
    )
    return pruner, graph_backend, budget_estimator, hub_detector


def test_graph_trace_required_keys(pruner_dependencies):
    graph_pruner, _, _, _ = pruner_dependencies
    
    schema = {
        "tables": {
            "A": {"columns": [{"name": "id"}], "foreign_keys": []},
            "B": {"columns": [{"name": "id"}], "foreign_keys": []}
        },
        "graph": {"nodes": ["A", "B"], "edges": []}
    }
    
    candidates = [
        CandidateAggregate(table="A", signals=[CandidateSignal(source="test", score=0.9, reason="test")]),
        CandidateAggregate(table="B", signals=[CandidateSignal(source="test", score=0.8, reason="test")])
    ]
    
    policy = TraversalPolicy()
    
    selected_tables, trace = graph_pruner.select_subgraph(schema, candidates, policy)
    
    required = [
        "policy",
        "path_mode",
        "hub_tables",
        "seed_candidates",
        "seed_tables",
        "expanded_neighbors",
        "skipped_hubs",
        "skipped_budget",
        "skipped_max_tables",
        "path_repairs",
        "estimated_tokens",
        "selected_tables",
    ]
    
    for key in required:
        assert key in trace, f"Missing key in graph_trace: {key}"
        
    assert isinstance(trace["selected_tables"], list)
    assert trace["selected_tables"] == sorted(list(selected_tables))


def test_graph_trace_policy_contains_traversal_policy(pruner_dependencies):
    graph_pruner, _, _, _ = pruner_dependencies
    
    schema = {
        "tables": {
            "A": {"columns": [{"name": "id"}], "foreign_keys": []}
        },
        "graph": {"nodes": ["A"], "edges": []}
    }
    
    candidates = [
        CandidateAggregate(table="A", signals=[CandidateSignal(source="test", score=0.9, reason="test")])
    ]
    
    policy = TraversalPolicy(
        min_candidate_score=0.55,
        min_edge_weight=0.1,
        max_depth=3,
        max_neighbors_per_seed=5,
        exclude_hubs=True,
        allow_hubs_as_connectors=False,
        token_budget=1500,
        max_tables=7,
        path_mode="undirected_weighted"
    )
    
    _, trace = graph_pruner.select_subgraph(schema, candidates, policy)
    
    policy_trace = trace["policy"]
    
    assert policy_trace["min_candidate_score"] == policy.min_candidate_score
    assert policy_trace["min_edge_weight"] == policy.min_edge_weight
    assert policy_trace["max_depth"] == policy.max_depth
    assert policy_trace["max_neighbors_per_seed"] == policy.max_neighbors_per_seed
    assert policy_trace["exclude_hubs"] == policy.exclude_hubs
    assert policy_trace["allow_hubs_as_connectors"] == policy.allow_hubs_as_connectors
    assert policy_trace["token_budget"] == policy.token_budget
    assert policy_trace["max_tables"] == policy.max_tables
    assert policy_trace["path_mode"] == policy.path_mode


def test_schema_pruner_success_debug_trace_contract():
    mock_manager = MagicMock()
    mock_schema = {
        "tables": {
            "HST_DOKTOR": {"columns": [{"name": "id"}], "foreign_keys": []},
            "HST_HASTA": {"columns": [{"name": "id"}], "foreign_keys": []}
        },
        "graph": {
            "nodes": ["HST_DOKTOR", "HST_HASTA"],
            "edges": []
        }
    }
    mock_manager.load_schema.return_value = mock_schema
    
    pruner = SchemaPruner(schema_manager=mock_manager)
    aqr = {"natural_query": "doktor ve hasta", "entities": ["doktor", "hasta"]}
    
    result = pruner.prune_schema(aqr)
    
    assert result["pruned"] is True
    assert "debug_trace" in result
    
    dt = result["debug_trace"]
    
    # Check minimum required keys in success debug_trace
    assert "rag_matches" in dt
    assert "candidate_signals" in dt
    assert "selected_tables" in dt
    assert "graph_trace" in dt
    
    # Check minimum top-level keys
    assert "estimated_tokens" in result
    assert "tables" in result
    assert "graph" in result
    assert "nodes" in result["graph"]
    assert "edges" in result["graph"]
    
    # candidate_signals list format check
    assert isinstance(dt["candidate_signals"], list)
    for signal_agg in dt["candidate_signals"]:
        assert "table" in signal_agg
        assert "final_score" in signal_agg
        assert "signals" in signal_agg
        assert isinstance(signal_agg["signals"], list)
        
    # selected_tables sorted/stable check
    assert isinstance(dt["selected_tables"], list)
    assert dt["selected_tables"] == sorted(dt["selected_tables"])
    
    # estimated_tokens graph_trace alignment check
    assert result["estimated_tokens"] == dt["graph_trace"]["estimated_tokens"]


def test_schema_pruner_no_candidate_failure_contract():
    mock_manager = MagicMock()
    mock_schema = {
        "tables": {
            "HST_DOKTOR": {"columns": [{"name": "id"}], "foreign_keys": []}
        },
        "graph": {"nodes": ["HST_DOKTOR"], "edges": []}
    }
    mock_manager.load_schema.return_value = mock_schema
    
    pruner = SchemaPruner(schema_manager=mock_manager)
    # A query that matches absolutely nothing
    aqr = {"natural_query": "xyz abc", "entities": ["xyz"]}
    
    result = pruner.prune_schema(aqr)
    
    assert result["pruned"] is False
    assert "error" in result
    assert "original_table_count" in result
    assert "pruned_table_count" in result
    assert result["pruned_table_count"] == 0
    assert "tables" in result
    assert "graph" in result
    
    # Even on failure, debug_trace should be stable if present
    assert "debug_trace" in result
    dt = result["debug_trace"]
    assert "rag_matches" in dt
    assert "candidate_signals" in dt
    assert dt["candidate_signals"] == []
    assert "selected_tables" in dt
    assert dt["selected_tables"] == []
    assert "graph_trace" in dt
    assert dt["graph_trace"] == {}


def test_schema_pruner_traversal_failure_contract():
    mock_manager = MagicMock()
    mock_schema = {
        "tables": {
            "HST_DOKTOR": {"columns": [{"name": "id"}], "foreign_keys": []}
        },
        "graph": {"nodes": ["HST_DOKTOR"], "edges": []}
    }
    mock_manager.load_schema.return_value = mock_schema
    
    class RejectAllBudgetGraphPruner:
        def select_subgraph(self, schema, candidates, policy):
            # Simulate a scenario where candidates are resolved but budget is exceeded, so 0 selected
            return set(), {
                "policy": {},
                "path_mode": "undirected_weighted",
                "hub_tables": [],
                "seed_candidates": [],
                "seed_tables": [],
                "expanded_neighbors": [],
                "skipped_hubs": [],
                "skipped_budget": [{"table": "HST_DOKTOR", "reason": "token_budget_exceeded"}],
                "skipped_max_tables": [],
                "path_repairs": [],
                "estimated_tokens": 0,
                "selected_tables": [],
            }
            
    pruner = SchemaPruner(schema_manager=mock_manager, graph_pruner=RejectAllBudgetGraphPruner())
    aqr = {"natural_query": "doktor", "entities": ["doktor"]}
    
    result = pruner.prune_schema(aqr)
    
    assert result["pruned"] is False
    assert "error" in result
    assert result["pruned_table_count"] == 0
    assert "tables" in result
    assert "graph" in result
    
    assert "debug_trace" in result
    dt = result["debug_trace"]
    assert "rag_matches" in dt
    assert "candidate_signals" in dt
    assert len(dt["candidate_signals"]) > 0
    assert "selected_tables" in dt
    assert dt["selected_tables"] == []
    assert "graph_trace" in dt
    assert len(dt["graph_trace"]["skipped_budget"]) == 1
