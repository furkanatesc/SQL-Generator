import pytest
from unittest.mock import MagicMock
from app.schema_graph.networkx_backend import NetworkXGraphBackend
from app.schema_pruner import SchemaPruner
from app.schema_graph.traversal_policy import TraversalPolicy
from app.schema_graph.hub_detector import HubDetector

def test_path_mode_affects_shortest_path():
    backend = NetworkXGraphBackend()
    # A -> B, B -> C
    schema = {
        "tables": {"A": {}, "B": {}, "C": {}},
        "graph": {
            "edges": [
                {"source": "A", "target": "B"},
                {"source": "B", "target": "C"}
            ]
        }
    }
    backend.build_graph(schema)
    
    # Path from C to A
    directed_path = backend.shortest_path("C", "A", mode="directed_weighted")
    assert directed_path == []
    
    undirected_path = backend.shortest_path("C", "A", mode="undirected_weighted")
    assert undirected_path == ["C", "B", "A"]

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

def test_hub_detector_returns_reasons():
    detector = HubDetector()
    edges = [{"source": "HUB_TABLE", "target": f"T_{i}"} for i in range(20)]
    schema = {
        "tables": {
            "KULLANICI": {},      # known_name
            "SYS_LOG": {},        # token_match
            "HUB_TABLE": {},      # degree_p95
            "NORMAL_TABLE": {}    # none
        },
        "graph": {"edges": edges}
    }
    
    reasons = detector.detect_hub_reasons(schema)
    
    assert "KULLANICI" in reasons
    assert "known_name" in reasons["KULLANICI"]
    
    assert "SYS_LOG" in reasons
    assert "token_match" in reasons["SYS_LOG"]
    
    assert "HUB_TABLE" in reasons
    assert "degree_p95" in reasons["HUB_TABLE"]
    
    assert "NORMAL_TABLE" not in reasons

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
