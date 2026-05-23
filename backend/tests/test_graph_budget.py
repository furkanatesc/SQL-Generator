import pytest
from unittest.mock import MagicMock
from app.schema_pruner import SchemaPruner
from app.schema_graph.traversal_policy import TraversalPolicy
from app.schema_graph.hub_detector import HubDetector
from app.schema_graph.token_budget import TokenBudgetEstimator

def test_schema_pruner_respects_max_tables():
    pruner = SchemaPruner()
    
    # Use a small budget so we can test limits, or just set max_tables to 2
    policy = TraversalPolicy(max_tables=2, token_budget=100000, min_candidate_score=0.45)
    
    schema = {
        "tables": {
            "TABLE_A": {"columns": [], "foreign_keys": []},
            "TABLE_B": {"columns": [], "foreign_keys": []},
            "TABLE_C": {"columns": [], "foreign_keys": []}
        },
        "graph": {"edges": []}
    }
    
    # Mock resolve_entities to return 3 candidates
    pruner.schema_manager = MagicMock()
    pruner.schema_manager.load_schema.return_value = schema
    
    candidate_A = MagicMock()
    candidate_A.table = "TABLE_A"
    candidate_A.score = 0.9
    
    candidate_B = MagicMock()
    candidate_B.table = "TABLE_B"
    candidate_B.score = 0.8
    
    candidate_C = MagicMock()
    candidate_C.table = "TABLE_C"
    candidate_C.score = 0.7
    
    pruner.resolve_entities = MagicMock(return_value=([candidate_A, candidate_B, candidate_C], {}))
    
    aqr = {"natural_query": "test"}
    result = pruner.prune_schema(aqr, policy=policy)
    
    assert result["pruned_table_count"] == 2
    assert "TABLE_C" not in result["tables"]
    
    trace = result["debug_trace"]["graph_trace"]
    assert any(s["table"] == "TABLE_C" for s in trace["skipped_max_tables"])

def test_schema_pruner_integration_uses_detectors():
    pruner = SchemaPruner()
    
    assert isinstance(pruner.budget_estimator, TokenBudgetEstimator)
    assert isinstance(pruner.hub_detector, HubDetector)
    
    # Mock methods to verify they are called
    pruner.hub_detector.detect_hub_reasons = MagicMock(return_value={"HUB_TABLE": ["degree_p95"]})
    pruner.budget_estimator.estimate_table_cost = MagicMock(return_value=10)
    pruner.budget_estimator.can_add = MagicMock(return_value=True)
    
    schema = {
        "tables": {
            "TABLE_A": {"columns": [], "foreign_keys": []}
        },
        "graph": {"edges": []}
    }
    
    pruner.schema_manager = MagicMock()
    pruner.schema_manager.load_schema.return_value = schema
    
    candidate_A = MagicMock()
    candidate_A.table = "TABLE_A"
    candidate_A.score = 0.9
    
    pruner.resolve_entities = MagicMock(return_value=([candidate_A], {}))
    
    aqr = {"natural_query": "test"}
    policy = TraversalPolicy(min_candidate_score=0.45)
    result = pruner.prune_schema(aqr, policy=policy)
    
    pruner.hub_detector.detect_hub_reasons.assert_called_once_with(schema)
    pruner.budget_estimator.estimate_table_cost.assert_called_with("TABLE_A", schema["tables"]["TABLE_A"])
    
    trace = result["debug_trace"]["graph_trace"]
    assert any(h["table"] == "HUB_TABLE" for h in trace["hub_tables"])

def test_allow_hubs_as_connectors_false_blocks_hub_connector():
    pruner = SchemaPruner()
    policy = TraversalPolicy(
        min_candidate_score=0.45,
        exclude_hubs=True,
        allow_hubs_as_connectors=False,
        max_tables=10,
        token_budget=1000
    )
    
    # A - KULLANICI - B
    schema = {
        "tables": {
            "A": {"columns": [], "foreign_keys": []},
            "B": {"columns": [], "foreign_keys": []},
            "KULLANICI": {"columns": [], "foreign_keys": []}
        },
        "graph": {
            "edges": [
                {"source": "A", "target": "KULLANICI"},
                {"source": "KULLANICI", "target": "B"}
            ]
        }
    }
    pruner.schema_manager = MagicMock()
    pruner.schema_manager.load_schema.return_value = schema
    
    candidate_A = MagicMock()
    candidate_A.table = "A"
    candidate_A.score = 0.9
    
    candidate_B = MagicMock()
    candidate_B.table = "B"
    candidate_B.score = 0.8
    
    pruner.resolve_entities = MagicMock(return_value=([candidate_A, candidate_B], {}))
    
    result = pruner.prune_schema({"natural_query": "test"}, policy=policy)
    
    # KULLANICI should not be added
    assert "KULLANICI" not in result["tables"]
    
    trace = result["debug_trace"]["graph_trace"]
    # skipped_hubs should contain KULLANICI with phase path_repair
    skipped = [s for s in trace["skipped_hubs"] if s["table"] == "KULLANICI" and s["phase"] == "path_repair"]
    assert len(skipped) > 0
    assert skipped[0]["reason"] == "hub_connector_not_allowed"

def test_allow_hubs_as_connectors_true_allows_hub_connector():
    pruner = SchemaPruner()
    policy = TraversalPolicy(
        min_candidate_score=0.45,
        exclude_hubs=True,
        allow_hubs_as_connectors=True,
        max_tables=10,
        token_budget=1000
    )
    
    schema = {
        "tables": {
            "A": {"columns": [], "foreign_keys": []},
            "B": {"columns": [], "foreign_keys": []},
            "KULLANICI": {"columns": [], "foreign_keys": []}
        },
        "graph": {
            "edges": [
                {"source": "A", "target": "KULLANICI"},
                {"source": "KULLANICI", "target": "B"}
            ]
        }
    }
    pruner.schema_manager = MagicMock()
    pruner.schema_manager.load_schema.return_value = schema
    
    candidate_A = MagicMock()
    candidate_A.table = "A"
    candidate_A.score = 0.9
    
    candidate_B = MagicMock()
    candidate_B.table = "B"
    candidate_B.score = 0.8
    
    pruner.resolve_entities = MagicMock(return_value=([candidate_A, candidate_B], {}))
    
    result = pruner.prune_schema({"natural_query": "test"}, policy=policy)
    
    # KULLANICI SHOULD be added as connector
    assert "KULLANICI" in result["tables"]

def test_graph_trace_skipped_items_are_objects():
    pruner = SchemaPruner()
    # A single policy setting that triggers everything
    policy = TraversalPolicy(
        min_candidate_score=0.45,
        exclude_hubs=True,
        allow_hubs_as_connectors=False,
        max_tables=1,   # to force max_tables_reached
        token_budget=10 # to force budget exceeded
    )
    
    schema = {
        "tables": {
            "A": {"columns": [], "foreign_keys": []},
            "KULLANICI": {"columns": [], "foreign_keys": []},
            "EXPENSIVE": {"columns": [{} for _ in range(100)], "foreign_keys": []},
            "EXTRA": {"columns": [], "foreign_keys": []}
        },
        "graph": {
            "edges": [
                {"source": "A", "target": "KULLANICI"},
                {"source": "A", "target": "EXPENSIVE"},
                {"source": "A", "target": "EXTRA"}
            ]
        }
    }
    pruner.schema_manager = MagicMock()
    pruner.schema_manager.load_schema.return_value = schema
    
    candidate_A = MagicMock()
    candidate_A.table = "A"
    candidate_A.score = 0.9
    
    pruner.resolve_entities = MagicMock(return_value=([candidate_A], {}))
    
    result = pruner.prune_schema({"natural_query": "test"}, policy=policy)
    
    trace = result["debug_trace"]["graph_trace"]
    
    assert len(trace["skipped_hubs"]) > 0
    assert isinstance(trace["skipped_hubs"][0], dict)
    
    assert len(trace["skipped_max_tables"]) > 0
    assert isinstance(trace["skipped_max_tables"][0], dict)
