import pytest
from app.schema_graph.graph_pruner import GraphPruner
from app.schema_graph.traversal_policy import TraversalPolicy
from app.schema_graph.token_budget import TokenBudgetEstimator
from app.schema_graph.hub_detector import HubDetector
from app.schema_graph.networkx_backend import NetworkXGraphBackend
from app.nlp.text_normalizer import TextNormalizer
from app.schema_candidates import CandidateAggregate, CandidateSignal

@pytest.fixture
def graph_pruner():
    normalizer = TextNormalizer()
    return GraphPruner(
        graph_backend=NetworkXGraphBackend(),
        budget_estimator=TokenBudgetEstimator(),
        hub_detector=HubDetector(normalizer=normalizer)
    )

def test_graph_pruner_selects_seed_tables_above_threshold(graph_pruner):
    schema = {
        "tables": {
            "A": {"columns": [{"name": "id"}], "foreign_keys": []},
            "B": {"columns": [{"name": "id"}], "foreign_keys": []}
        },
        "graph": {"nodes": ["A", "B"], "edges": []}
    }
    
    candidates = [
        CandidateAggregate(table="A", signals=[CandidateSignal(source="test", score=0.9, reason="test")]),
        CandidateAggregate(table="B", signals=[CandidateSignal(source="test", score=0.2, reason="test")])
    ]
    
    policy = TraversalPolicy(min_candidate_score=0.45)
    
    selected_tables, trace = graph_pruner.select_subgraph(schema, candidates, policy)
    
    assert "A" in selected_tables
    assert "B" not in selected_tables
    assert "A" in trace["seed_tables"]
    assert "B" not in trace["seed_tables"]
    
    seed_cands = [c["table"] for c in trace["seed_candidates"]]
    assert "A" in seed_cands
    assert "B" not in seed_cands

def test_graph_pruner_respects_budget_for_seeds(graph_pruner):
    schema = {
        "tables": {
            "A": {"columns": [{"name": f"col_{i}"} for i in range(100)], "foreign_keys": []}, # Expensive table
        },
        "graph": {"nodes": ["A"], "edges": []}
    }
    
    candidates = [
        CandidateAggregate(table="A", signals=[CandidateSignal(source="test", score=0.9, reason="test")])
    ]
    
    policy = TraversalPolicy(min_candidate_score=0.45, token_budget=10) # very low budget
    
    selected_tables, trace = graph_pruner.select_subgraph(schema, candidates, policy)
    
    assert "A" not in selected_tables
    assert len(trace["skipped_budget"]) > 0
    assert trace["skipped_budget"][0]["table"] == "A"
    assert trace["skipped_budget"][0]["phase"] == "seed_selection"

def test_graph_pruner_expands_neighbors_within_depth_and_limit(graph_pruner):
    schema = {
        "tables": {
            "A": {"columns": [{"name": "id"}], "foreign_keys": [{"referenced_table": "B"}, {"referenced_table": "C"}, {"referenced_table": "D"}]},
            "B": {"columns": [{"name": "id"}], "foreign_keys": []},
            "C": {"columns": [{"name": "id"}], "foreign_keys": []},
            "D": {"columns": [{"name": "id"}], "foreign_keys": []},
        },
        "graph": {
            "nodes": ["A", "B", "C", "D"], 
            "edges": [
                {"source": "A", "target": "B"},
                {"source": "A", "target": "C"},
                {"source": "A", "target": "D"}
            ]
        }
    }
    
    candidates = [
        CandidateAggregate(table="A", signals=[CandidateSignal(source="test", score=0.9, reason="test")])
    ]
    
    policy = TraversalPolicy(min_candidate_score=0.45, max_neighbors_per_seed=1, max_depth=1)
    
    selected_tables, trace = graph_pruner.select_subgraph(schema, candidates, policy)
    
    assert "A" in selected_tables
    # Since max_neighbors_per_seed=1, only 1 neighbor should be added.
    # Total selected should be 2.
    assert len(selected_tables) == 2
    assert len(trace["expanded_neighbors"]) == 1

def test_graph_pruner_blocks_hub_expansion(graph_pruner):
    schema = {
        "tables": {
            "A": {"columns": [{"name": "id"}], "foreign_keys": [{"referenced_table": "KULLANICI"}]},
            "KULLANICI": {"columns": [{"name": "id"}], "foreign_keys": []}
        },
        "graph": {
            "nodes": ["A", "KULLANICI"],
            "edges": [{"source": "A", "target": "KULLANICI"}]
        }
    }
    
    candidates = [
        CandidateAggregate(table="A", signals=[CandidateSignal(source="test", score=0.9, reason="test")])
    ]
    
    policy = TraversalPolicy(min_candidate_score=0.45, exclude_hubs=True)
    
    selected_tables, trace = graph_pruner.select_subgraph(schema, candidates, policy)
    
    assert "A" in selected_tables
    assert "KULLANICI" not in selected_tables
    assert len(trace["skipped_hubs"]) > 0
    assert trace["skipped_hubs"][0]["table"] == "KULLANICI"
    assert trace["skipped_hubs"][0]["phase"] == "expansion"

def test_graph_pruner_path_repair_adds_connector(graph_pruner):
    schema = {
        "tables": {
            "A": {"columns": [{"name": "id"}], "foreign_keys": [{"referenced_table": "CONNECTOR"}]},
            "CONNECTOR": {"columns": [{"name": "id"}], "foreign_keys": [{"referenced_table": "B"}]},
            "B": {"columns": [{"name": "id"}], "foreign_keys": []}
        },
        "graph": {
            "nodes": ["A", "CONNECTOR", "B"],
            "edges": [
                {"source": "A", "target": "CONNECTOR"},
                {"source": "CONNECTOR", "target": "B"}
            ]
        }
    }
    
    candidates = [
        CandidateAggregate(table="A", signals=[CandidateSignal(source="test", score=0.9, reason="test")]),
        CandidateAggregate(table="B", signals=[CandidateSignal(source="test", score=0.9, reason="test")])
    ]
    
    # max_depth=0 stops expansion, so only seeds are selected.
    # then path_repair should add CONNECTOR.
    policy = TraversalPolicy(min_candidate_score=0.45, max_depth=0)
    
    selected_tables, trace = graph_pruner.select_subgraph(schema, candidates, policy)
    
    assert "A" in selected_tables
    assert "B" in selected_tables
    assert "CONNECTOR" in selected_tables
    
    assert len(trace["path_repairs"]) > 0
    repair = trace["path_repairs"][0]
    assert "CONNECTOR" in repair["added"]

def test_graph_pruner_path_repair_blocks_hub_connector_by_default(graph_pruner):
    schema = {
        "tables": {
            "A": {"columns": [{"name": "id"}], "foreign_keys": [{"referenced_table": "KULLANICI"}]},
            "KULLANICI": {"columns": [{"name": "id"}], "foreign_keys": [{"referenced_table": "B"}]},
            "B": {"columns": [{"name": "id"}], "foreign_keys": []}
        },
        "graph": {
            "nodes": ["A", "KULLANICI", "B"],
            "edges": [
                {"source": "A", "target": "KULLANICI"},
                {"source": "KULLANICI", "target": "B"}
            ]
        }
    }
    
    candidates = [
        CandidateAggregate(table="A", signals=[CandidateSignal(source="test", score=0.9, reason="test")]),
        CandidateAggregate(table="B", signals=[CandidateSignal(source="test", score=0.9, reason="test")])
    ]
    
    policy = TraversalPolicy(min_candidate_score=0.45, max_depth=0, exclude_hubs=True, allow_hubs_as_connectors=False)
    
    selected_tables, trace = graph_pruner.select_subgraph(schema, candidates, policy)
    
    assert "A" in selected_tables
    assert "B" in selected_tables
    assert "KULLANICI" not in selected_tables
    
    assert len(trace["skipped_hubs"]) > 0
    assert trace["skipped_hubs"][0]["table"] == "KULLANICI"
    assert trace["skipped_hubs"][0]["phase"] == "path_repair"
    
    if trace["path_repairs"]:
        repair = trace["path_repairs"][0]
        assert "KULLANICI" in repair["skipped"]

def test_graph_pruner_path_repair_allows_hub_connector_when_enabled(graph_pruner):
    schema = {
        "tables": {
            "A": {"columns": [{"name": "id"}], "foreign_keys": [{"referenced_table": "KULLANICI"}]},
            "KULLANICI": {"columns": [{"name": "id"}], "foreign_keys": [{"referenced_table": "B"}]},
            "B": {"columns": [{"name": "id"}], "foreign_keys": []}
        },
        "graph": {
            "nodes": ["A", "KULLANICI", "B"],
            "edges": [
                {"source": "A", "target": "KULLANICI"},
                {"source": "KULLANICI", "target": "B"}
            ]
        }
    }
    
    candidates = [
        CandidateAggregate(table="A", signals=[CandidateSignal(source="test", score=0.9, reason="test")]),
        CandidateAggregate(table="B", signals=[CandidateSignal(source="test", score=0.9, reason="test")])
    ]
    
    policy = TraversalPolicy(min_candidate_score=0.45, max_depth=0, exclude_hubs=True, allow_hubs_as_connectors=True)
    
    selected_tables, trace = graph_pruner.select_subgraph(schema, candidates, policy)
    
    assert "A" in selected_tables
    assert "B" in selected_tables
    assert "KULLANICI" in selected_tables

def test_graph_pruner_trace_contains_expected_keys(graph_pruner):
    schema = {
        "tables": {
            "A": {"columns": [{"name": "id"}], "foreign_keys": []},
        },
        "graph": {"nodes": ["A"], "edges": []}
    }
    
    candidates = [
        CandidateAggregate(table="A", signals=[CandidateSignal(source="test", score=0.9, reason="test")])
    ]
    
    policy = TraversalPolicy(min_candidate_score=0.45)
    
    selected_tables, trace = graph_pruner.select_subgraph(schema, candidates, policy)
    
    expected_keys = [
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
        "selected_tables"
    ]
    
    for key in expected_keys:
        assert key in trace

def test_graph_trace_policy_is_explicit_dict(graph_pruner):
    schema = {
        "tables": {"A": {"columns": [{"name": "id"}], "foreign_keys": []}},
        "graph": {"nodes": ["A"], "edges": []}
    }
    
    candidates = [
        CandidateAggregate(table="A", signals=[CandidateSignal(source="test", score=0.9, reason="test")])
    ]
    
    policy = TraversalPolicy(min_candidate_score=0.45)
    
    _, trace = graph_pruner.select_subgraph(schema, candidates, policy)
    
    # Assert policy is a standard dictionary not the class internal dict if it were changed.
    assert isinstance(trace["policy"], dict)
    assert "min_candidate_score" in trace["policy"]
    assert "exclude_hubs" in trace["policy"]

def test_graph_trace_selected_tables_are_sorted(graph_pruner):
    schema = {
        "tables": {
            "C": {"columns": [{"name": "id"}], "foreign_keys": []},
            "A": {"columns": [{"name": "id"}], "foreign_keys": []},
            "B": {"columns": [{"name": "id"}], "foreign_keys": []}
        },
        "graph": {"nodes": ["A", "B", "C"], "edges": []}
    }
    
    candidates = [
        CandidateAggregate(table="C", signals=[CandidateSignal(source="test", score=0.9, reason="test")]),
        CandidateAggregate(table="A", signals=[CandidateSignal(source="test", score=0.9, reason="test")]),
        CandidateAggregate(table="B", signals=[CandidateSignal(source="test", score=0.9, reason="test")])
    ]
    
    policy = TraversalPolicy(min_candidate_score=0.45)
    
    selected_tables, trace = graph_pruner.select_subgraph(schema, candidates, policy)
    
    assert trace["selected_tables"] == ["A", "B", "C"]

def test_graph_trace_skip_objects_have_phase_and_reason(graph_pruner):
    schema = {
        "tables": {
            "A": {"columns": [{"name": "id"}], "foreign_keys": [{"referenced_table": "KULLANICI"}]},
            "KULLANICI": {"columns": [{"name": "id"}], "foreign_keys": []}, # Hub
            "EXPENSIVE": {"columns": [{"name": f"col_{i}"} for i in range(100)], "foreign_keys": []}
        },
        "graph": {
            "nodes": ["A", "KULLANICI", "EXPENSIVE"],
            "edges": [{"source": "A", "target": "KULLANICI"}]
        }
    }
    
    candidates = [
        CandidateAggregate(table="A", signals=[CandidateSignal(source="test", score=0.9, reason="test")]),
        CandidateAggregate(table="EXPENSIVE", signals=[CandidateSignal(source="test", score=0.9, reason="test")])
    ]
    
    # max_tables=1 to trigger max_tables skip, very low budget to trigger budget skip
    policy = TraversalPolicy(min_candidate_score=0.45, token_budget=10, max_tables=1, exclude_hubs=True)
    
    # By picking A first (if lucky) or EXPENSIVE first, we can force skips. 
    # Since A has lower cost than EXPENSIVE, A might get selected first, triggering budget or max_tables on EXPENSIVE.
    # To reliably trigger skips, let's just inspect what is skipped.
    
    _, trace = graph_pruner.select_subgraph(schema, candidates, policy)
    
    for key in ["skipped_hubs", "skipped_budget", "skipped_max_tables"]:
        for item in trace[key]:
            assert "table" in item
            assert "phase" in item
            assert "reason" in item
