import pytest
from unittest.mock import MagicMock
from app.schema_pruner import SchemaPruner
from app.schema_graph.traversal_policy import TraversalPolicy
from app.schema_candidates import CandidateAggregate, CandidateSignal

class FakeGraphPruner:
    def select_subgraph(self, schema, candidates, policy):
        return {"HST_DOKTOR"}, {
            "policy": {},
            "path_mode": "undirected_weighted",
            "hub_tables": [],
            "seed_candidates": [],
            "seed_tables": ["HST_DOKTOR"],
            "expanded_neighbors": [],
            "skipped_hubs": [],
            "skipped_budget": [],
            "skipped_max_tables": [],
            "path_repairs": [],
            "estimated_tokens": 42,
            "selected_tables": ["HST_DOKTOR"],
        }

class EmptyFakeGraphPruner:
    def select_subgraph(self, schema, candidates, policy):
        return set(), {
            "policy": {},
            "path_mode": "undirected_weighted",
            "hub_tables": [],
            "seed_candidates": [],
            "seed_tables": [],
            "expanded_neighbors": [],
            "skipped_hubs": [],
            "skipped_budget": [],
            "skipped_max_tables": [],
            "path_repairs": [],
            "estimated_tokens": 0,
            "selected_tables": [],
        }

def test_schema_pruner_delegates_to_graph_pruner():
    mock_manager = MagicMock()
    mock_schema = {
        "tables": {
            "HST_DOKTOR": {"columns": [{"name": "id"}], "foreign_keys": []}
        }
    }
    mock_manager.load_schema.return_value = mock_schema
    
    pruner = SchemaPruner(schema_manager=mock_manager, graph_pruner=FakeGraphPruner())
    
    # Needs to match something to get candidates
    aqr = {"natural_query": "doktor", "entities": ["doktor"]}
    
    result = pruner.prune_schema(aqr)
    
    assert result["pruned"] is True
    assert "HST_DOKTOR" in result["tables"]
    assert result["estimated_tokens"] == 42
    assert "graph_trace" in result["debug_trace"]
    assert result["debug_trace"]["graph_trace"]["estimated_tokens"] == 42

def test_prune_schema_returns_error_when_candidates_exist_but_no_tables_selected():
    mock_manager = MagicMock()
    mock_schema = {
        "tables": {
            "HST_DOKTOR": {"columns": [{"name": "id"}], "foreign_keys": []}
        }
    }
    mock_manager.load_schema.return_value = mock_schema
    
    pruner = SchemaPruner(schema_manager=mock_manager, graph_pruner=EmptyFakeGraphPruner())
    
    aqr = {"natural_query": "doktor", "entities": ["doktor"]}
    
    result = pruner.prune_schema(aqr)
    
    assert result["pruned"] is False
    assert result["pruned_table_count"] == 0
    assert "Aday tablolar bulundu" in result["error"]
    assert "graph_trace" in result["debug_trace"]
