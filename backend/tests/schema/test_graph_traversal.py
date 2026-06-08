import pytest
import json
import os
from app.schema.schema_contract import RelationshipType
from app.schema.graph_traversal import find_join_paths
from app.schema.schema_adapter import from_legacy_schema

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures", "schema")

def load_fixture(filename: str):
    with open(os.path.join(FIXTURES_DIR, filename), "r", encoding="utf-8") as f:
        data = json.load(f)
    return from_legacy_schema(data, dialect="unknown")

def test_explicit_path_beats_implicit_path():
    schema = load_fixture("graph_traversal_ambiguous_schema.json")
    paths = find_join_paths(schema, "orders", "users")
    
    assert len(paths) > 0
    best = paths[0]
    
    assert best.edges[0].relationship_type == RelationshipType.EXPLICIT
    assert best.tables == ["orders", "users"]

def test_fuzzy_edges_are_excluded_by_default():
    schema = load_fixture("graph_traversal_fuzzy_schema.json")
    paths = find_join_paths(schema, "employees", "departments")
    assert paths == []

def test_fuzzy_edges_can_be_enabled_explicitly():
    schema = load_fixture("graph_traversal_fuzzy_schema.json")
    paths = find_join_paths(schema, "employees", "departments", allow_fuzzy=True)
    
    assert len(paths) == 1
    assert paths[0].edges[0].relationship_type == RelationshipType.IMPLICIT_FUZZY

def test_graph_traversal_is_cycle_safe():
    schema = load_fixture("graph_traversal_cycle_schema.json")
    # orders -> users -> payments -> orders ...
    # This should safely terminate.
    paths = find_join_paths(schema, "users", "payments", max_depth=4)
    
    assert len(paths) > 0
    assert all(path.path_length <= 4 for path in paths)
    assert paths[0].tables == ["users", "orders", "payments"]

def test_join_path_selection_is_deterministic_for_equal_scores():
    schema = load_fixture("graph_traversal_equal_score_schema.json")
    # Path through b: a -> b -> d
    # Path through c: a -> c -> d
    # Both have the exact same relationships and lengths, tie-breaker must decide based on lexical edge keys.
    # We want exactly deterministic output
    paths = find_join_paths(schema, "a", "d")
    
    # We should have exactly two paths
    assert len(paths) == 2
    
    # Check deterministic order using canonical lexical keys
    assert [p.tables for p in paths] == [
        ["a", "b", "d"],
        ["a", "c", "d"],
    ]

def test_join_path_respects_max_depth():
    schema = load_fixture("graph_traversal_long_chain_schema.json")
    # a -> b -> c -> d -> e (Length 4)
    paths = find_join_paths(schema, "a", "e", max_depth=2)
    assert paths == []
    
    paths_deep = find_join_paths(schema, "a", "e", max_depth=5)
    assert len(paths_deep) > 0
    assert paths_deep[0].tables == ["a", "b", "c", "d", "e"]
