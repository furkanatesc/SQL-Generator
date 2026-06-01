import os
import ast
import pytest
from app.schema_graph.traversal_policy import TraversalPolicy
from app.schema_graph.graph_pruner import GraphPruner
from app.schema_graph.networkx_backend import NetworkXGraphBackend
from app.schema_graph.token_budget import TokenBudgetEstimator
from app.schema_graph.hub_detector import HubDetector
from app.nlp.text_normalizer import TextNormalizer
from app.schema_candidates import CandidateAggregate, CandidateSignal

# Acceptance Criteria 1: schema_pruner.py does not import networkx
def test_schema_pruner_no_networkx_imports():
    app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    pruner_file = os.path.join(app_dir, "app", "schema_pruner.py")
    
    with open(pruner_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    tree = ast.parse(content)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert "networkx" not in alias.name, "schema_pruner.py should not import networkx directly"
        elif isinstance(node, ast.ImportFrom):
            assert node.module is not None
            assert "networkx" not in node.module, "schema_pruner.py should not import from networkx directly"

# Acceptance Criteria 2: networkx is ONLY used inside networkx_backend.py
def test_networkx_only_in_networkx_backend():
    app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    target_dir = os.path.join(app_dir, "app")
    
    for root, _, files in os.walk(target_dir):
        for file in files:
            if not file.endswith(".py"):
                continue
            
            file_path = os.path.join(root, file)
            # Skip networkx_backend.py itself
            if file == "networkx_backend.py":
                continue
                
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
                
            # Parse and check imports
            try:
                tree = ast.parse(content)
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            name_root = alias.name.split('.')[0]
                            assert name_root != "networkx", f"File {file} imports networkx directly!"
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            module_root = node.module.split('.')[0]
                            # Only disallow if the module imported from is exactly "networkx" or a submodule of it.
                            # We allow imports from "networkx_backend" because it is our own module.
                            assert module_root != "networkx", f"File {file} imports from networkx!"
            except SyntaxError:
                # In case of syntax errors in some files, fallback to simple string check of imports
                assert "import networkx" not in content, f"File {file} contains import networkx!"
                # Check for "from networkx " but not "from networkx_backend"
                if "from networkx" in content:
                    assert "from networkx_backend" in content or "from .networkx_backend" in content, f"File {file} contains from networkx!"

# Acceptance Criteria 3: TraversalPolicy min_candidate_score and min_edge_weight ayrımına sahip
def test_traversal_policy_distinct_thresholds():
    policy = TraversalPolicy()
    assert hasattr(policy, "min_candidate_score"), "TraversalPolicy is missing min_candidate_score"
    assert hasattr(policy, "min_edge_weight"), "TraversalPolicy is missing min_edge_weight"
    
    # Assert they are distinct and have separate default values
    assert policy.min_candidate_score == 0.45
    assert policy.min_edge_weight == 0.50

# Acceptance Criteria 4: GraphPruner bounded expansion (BFS)
def test_graph_pruner_bounded_expansion():
    normalizer = TextNormalizer()
    graph_backend = NetworkXGraphBackend()
    budget_estimator = TokenBudgetEstimator()
    hub_detector = HubDetector(normalizer=normalizer)
    
    pruner = GraphPruner(
        graph_backend=graph_backend,
        budget_estimator=budget_estimator,
        hub_detector=hub_detector
    )
    
    schema = {
        "tables": {
            "A": {"columns": [{"name": "id"}], "foreign_keys": [{"referenced_table": "B"}]},
            "B": {"columns": [{"name": "id"}], "foreign_keys": [{"referenced_table": "C"}]},
            "C": {"columns": [{"name": "id"}], "foreign_keys": []},
        },
        "graph": {
            "nodes": ["A", "B", "C"],
            "edges": [
                {"source": "A", "target": "B"},
                {"source": "B", "target": "C"}
            ]
        }
    }
    
    candidates = [
        CandidateAggregate(table="A", signals=[CandidateSignal(source="test", score=0.9, reason="test")])
    ]
    
    # max_depth = 1 should only expand to B, but not C
    policy = TraversalPolicy(min_candidate_score=0.45, max_depth=1, min_edge_weight=0.0)
    selected_tables, trace = pruner.select_subgraph(schema, candidates, policy)
    
    assert "A" in selected_tables
    assert "B" in selected_tables
    assert "C" not in selected_tables
    assert len(trace["expanded_neighbors"]) == 1
    assert trace["expanded_neighbors"][0]["to"] == "B"

# Acceptance Criteria 5: HubDetector hub tabloları dışlıyor
def test_hub_detector_exclusion_in_pruner():
    normalizer = TextNormalizer()
    graph_backend = NetworkXGraphBackend()
    budget_estimator = TokenBudgetEstimator()
    hub_detector = HubDetector(normalizer=normalizer)
    
    pruner = GraphPruner(
        graph_backend=graph_backend,
        budget_estimator=budget_estimator,
        hub_detector=hub_detector
    )
    
    # "KULLANICI" is a known hub name
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
    
    # Hub exclusion is True, so KULLANICI should be excluded from expansion
    policy = TraversalPolicy(min_candidate_score=0.45, exclude_hubs=True, min_edge_weight=0.0)
    selected_tables, trace = pruner.select_subgraph(schema, candidates, policy)
    
    assert "A" in selected_tables
    assert "KULLANICI" not in selected_tables
    assert len(trace["skipped_hubs"]) > 0
    assert trace["skipped_hubs"][0]["table"] == "KULLANICI"

# Acceptance Criteria 6: TokenBudgetEstimator budget aşımını engelliyor
def test_token_budget_estimator_blocks_overrun():
    normalizer = TextNormalizer()
    graph_backend = NetworkXGraphBackend()
    budget_estimator = TokenBudgetEstimator()
    hub_detector = HubDetector(normalizer=normalizer)
    
    pruner = GraphPruner(
        graph_backend=graph_backend,
        budget_estimator=budget_estimator,
        hub_detector=hub_detector
    )
    
    schema = {
        "tables": {
            "A": {"columns": [{"name": f"col_{i}"} for i in range(20)], "foreign_keys": []}, # cost: 8 + 60 = 68
        },
        "graph": {"nodes": ["A"], "edges": []}
    }
    
    candidates = [
        CandidateAggregate(table="A", signals=[CandidateSignal(source="test", score=0.9, reason="test")])
    ]
    
    # Set extremely low budget of 10 tokens (less than A's cost of 68 tokens)
    policy = TraversalPolicy(min_candidate_score=0.45, token_budget=10)
    selected_tables, trace = pruner.select_subgraph(schema, candidates, policy)
    
    assert "A" not in selected_tables
    assert len(trace["skipped_budget"]) > 0
    assert trace["skipped_budget"][0]["table"] == "A"
    assert trace["skipped_budget"][0]["reason"] == "token_budget_exceeded"

# Acceptance Criteria 7: Path repair ara tablo ekliyor
def test_path_repair_adds_connector_tables():
    normalizer = TextNormalizer()
    graph_backend = NetworkXGraphBackend()
    budget_estimator = TokenBudgetEstimator()
    hub_detector = HubDetector(normalizer=normalizer)
    
    pruner = GraphPruner(
        graph_backend=graph_backend,
        budget_estimator=budget_estimator,
        hub_detector=hub_detector
    )
    
    # A -> CONNECTOR -> B
    # max_depth=0 will prevent normal BFS expansion, forcing path repair to bridge them
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
    
    policy = TraversalPolicy(min_candidate_score=0.45, max_depth=0)
    selected_tables, trace = pruner.select_subgraph(schema, candidates, policy)
    
    assert "A" in selected_tables
    assert "B" in selected_tables
    assert "CONNECTOR" in selected_tables
    assert len(trace["path_repairs"]) > 0
    assert "CONNECTOR" in trace["path_repairs"][0]["added"]

# Acceptance Criteria 8: graph_trace selected / skipped_hubs / skipped_budget / expanded_neighbors / path_repairs gösteriyor
def test_graph_trace_contains_all_roadmap_keys():
    normalizer = TextNormalizer()
    graph_backend = NetworkXGraphBackend()
    budget_estimator = TokenBudgetEstimator()
    hub_detector = HubDetector(normalizer=normalizer)
    
    pruner = GraphPruner(
        graph_backend=graph_backend,
        budget_estimator=budget_estimator,
        hub_detector=hub_detector
    )
    
    schema = {
        "tables": {"A": {"columns": [{"name": "id"}], "foreign_keys": []}},
        "graph": {"nodes": ["A"], "edges": []}
    }
    
    candidates = [
        CandidateAggregate(table="A", signals=[CandidateSignal(source="test", score=0.9, reason="test")])
    ]
    
    policy = TraversalPolicy()
    _, trace = pruner.select_subgraph(schema, candidates, policy)
    
    required_keys = [
        "selected_tables",
        "skipped_hubs",
        "skipped_budget",
        "expanded_neighbors",
        "path_repairs"
    ]
    
    for key in required_keys:
        assert key in trace, f"graph_trace is missing required roadmap key: {key}"
