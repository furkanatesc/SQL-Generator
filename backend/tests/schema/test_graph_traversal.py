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
    # allow_fuzzy=True to discover the longer path that uses an implicit_fuzzy edge
    paths = find_join_paths(schema, "orders", "users", allow_fuzzy=True).paths

    assert [p.tables for p in paths] == [
        ["orders", "users"],
        ["orders", "audit_logs", "users"]
    ]
    
    best = paths[0]
    assert [e.relationship_type for e in best.edges] == [RelationshipType.EXPLICIT]
    assert best.tables == ["orders", "users"]

def test_direct_explicit_path_beats_longer_implicit_path():
    schema = load_fixture("graph_traversal_direct_explicit_vs_long_implicit_schema.json")
    paths = find_join_paths(schema, "orders", "users", allow_fuzzy=True).paths

    assert paths[0].tables == ["orders", "users"]
    assert [edge.relationship_type for edge in paths[0].edges] == [RelationshipType.EXPLICIT]

def test_fuzzy_edges_are_excluded_by_default():
    schema = load_fixture("graph_traversal_fuzzy_schema.json")
    paths = find_join_paths(schema, "employees", "departments").paths
    assert paths == []

def test_fuzzy_edges_can_be_enabled_explicitly():
    schema = load_fixture("graph_traversal_fuzzy_schema.json")
    paths = find_join_paths(schema, "employees", "departments", allow_fuzzy=True).paths

    assert [p.tables for p in paths] == [["employees", "departments"]]
    assert paths[0].edges[0].relationship_type == RelationshipType.IMPLICIT_FUZZY

def test_graph_traversal_is_cycle_safe():
    schema = load_fixture("graph_traversal_cycle_schema.json")
    # orders -> users -> payments -> orders ...
    paths = find_join_paths(schema, "users", "payments", max_depth=4).paths

    # Path length 1 edge vs 2 edges
    # Shorter path ("users" -> "payments") should come first because both have 100 priority
    assert [p.tables for p in paths] == [
        ["users", "payments"],
        ["users", "orders", "payments"]
    ]
    
    assert all(path.path_length <= 4 for path in paths)

def test_join_path_selection_is_deterministic_for_equal_scores():
    schema = load_fixture("graph_traversal_equal_score_schema.json")
    # Path through b: a -> b -> d
    # Path through c: a -> c -> d
    # Both have exactly the same relationships and lengths, tie-breaker decides.
    paths = find_join_paths(schema, "a", "d").paths

    # Check deterministic order using canonical lexical keys
    assert [p.tables for p in paths] == [
        ["a", "b", "d"],
        ["a", "c", "d"],
    ]

def test_join_path_respects_max_depth():
    schema = load_fixture("graph_traversal_long_chain_schema.json")
    # a -> b -> c -> d -> e (Length 4)
    paths = find_join_paths(schema, "a", "e", max_depth=2).paths
    assert paths == []

    paths_deep = find_join_paths(schema, "a", "e", max_depth=5).paths
    assert [p.tables for p in paths_deep] == [
        ["a", "b", "c", "d", "e"]
    ]

def test_max_paths_zero_or_negative_returns_empty():
    # Regression guard: pre-28.2 behavior for max_paths<=0 was an empty result.
    # The 28.2 kept-set _record() does `kept[-1]` once kept is trimmed back down
    # to empty, which would IndexError for max_paths<=0 without an early guard.
    schema = load_fixture("graph_traversal_equal_score_schema.json")
    result_zero = find_join_paths(schema, "a", "d", max_paths=0)
    assert result_zero.paths == []
    assert result_zero.node_visits == 0

    result_negative = find_join_paths(schema, "a", "d", max_paths=-1)
    assert result_negative.paths == []
    assert result_negative.node_visits == 0

def test_unreachable_target_returns_empty_without_visits():
    schema = load_fixture("graph_traversal_fuzzy_schema.json")
    # employees -> departments has only a fuzzy edge, excluded by default -> unreachable
    result = find_join_paths(schema, "employees", "departments")
    assert result.paths == []
    assert result.node_visits == 0  # BFS early-exit, no DFS performed


def _exhaustive_reference(schema, source, target, max_depth, max_paths, allow_fuzzy):
    """Naive all-paths enumeration mirroring pre-28.2 semantics (no pruning)."""
    from app.schema.schema_contract import RelationshipType
    from app.schema.relationship_priority import RELATIONSHIP_TYPE_PRIORITY
    adj = {t.name: [] for t in schema.tables}
    for rel in schema.relationships:
        if rel.relationship_type == RelationshipType.DISABLED:
            continue
        if not allow_fuzzy and rel.relationship_type == RelationshipType.IMPLICIT_FUZZY:
            continue
        if rel.source_table in adj: adj[rel.source_table].append(rel)
        if rel.target_table in adj: adj[rel.target_table].append(rel)
    found = []
    def walk(cur, tables, rels):
        if cur == target:
            found.append(list(tables)); return
        if len(rels) >= max_depth: return
        for rel in adj.get(cur, []):
            nxt = rel.target_table if rel.source_table == cur else rel.source_table
            if nxt in tables: continue
            tables.append(nxt); rels.append(rel)
            walk(nxt, tables, rels)
            tables.pop(); rels.pop()
    walk(source, [source], [])
    return found


def _exhaustive_reference_sorted(schema, source, target, max_depth, max_paths, allow_fuzzy):
    """
    Naive all-paths enumeration that reproduces the PRODUCTION sort/tie-break
    exactly: (-min_relationship_priority, -min_confidence, path_length, lexical
    edge key), where the lexical key uses the same from/to traversal-direction
    convention as find_join_paths (from = current node, to = next node,
    regardless of the underlying relationship's own source/target labels).
    Returns the top-`max_paths` table lists in production order, for an
    exact-order comparison against find_join_paths(...).paths.
    """
    from app.schema.relationship_priority import RELATIONSHIP_TYPE_PRIORITY
    adj = {t.name: [] for t in schema.tables}
    for rel in schema.relationships:
        if rel.relationship_type == RelationshipType.DISABLED:
            continue
        if not allow_fuzzy and rel.relationship_type == RelationshipType.IMPLICIT_FUZZY:
            continue
        if rel.source_table in adj: adj[rel.source_table].append(rel)
        if rel.target_table in adj: adj[rel.target_table].append(rel)
    scored = []
    def walk(cur, tables, steps):
        if cur == target:
            min_priority = 1000
            min_conf = 1.0
            lex_parts = []
            for c, n, rel in steps:
                p = RELATIONSHIP_TYPE_PRIORITY.get(rel.relationship_type, 0)
                if p < min_priority: min_priority = p
                conf = rel.confidence if rel.confidence is not None else 1.0
                if conf < min_conf: min_conf = conf
                if rel.source_table == c:
                    lex_parts.append(f"{c}.{rel.source_column}->{n}.{rel.target_column}")
                else:
                    lex_parts.append(f"{c}.{rel.target_column}->{n}.{rel.source_column}")
            key = (-min_priority, -min_conf, len(steps), "|".join(lex_parts))
            scored.append((key, list(tables)))
            return
        if len(steps) >= max_depth: return
        for rel in adj.get(cur, []):
            nxt = rel.target_table if rel.source_table == cur else rel.source_table
            if nxt in tables: continue
            tables.append(nxt); steps.append((cur, nxt, rel))
            walk(nxt, tables, steps)
            tables.pop(); steps.pop()
    walk(source, [source], [])
    scored.sort(key=lambda item: item[0])
    return [tables for _, tables in scored[:max_paths]]

def test_pruning_preserves_output_vs_reference():
    # medium schema with multiple parallel paths + a hub
    legacy = {"tables": {}}
    def tbl(name, fks):
        legacy["tables"][name] = {
            "columns": [{"name": "id", "primary_key": True}] +
                       [{"name": f"{fk[0]}_id"} for fk in fks],
            "foreign_keys": [{"column": f"{t}_id", "referenced_table": t,
                              "referenced_column": "id", "type": "explicit"} for t, _ in fks]}
    tbl("d", []); tbl("b", [("d", 0)]); tbl("c", [("d", 0)])
    tbl("a", [("b", 0), ("c", 0)])
    tbl("e", [("a", 0)]); tbl("f", [("a", 0)])  # extra branches off a
    schema = from_legacy_schema(legacy, "postgres")
    for src, tgt, depth, k in [("a", "d", 3, 5), ("a", "d", 3, 1), ("e", "d", 4, 5)]:
        got = [c.tables for c in find_join_paths(schema, src, tgt,
                                                 max_depth=depth, max_paths=k).paths]
        ref = _exhaustive_reference_sorted(schema, src, tgt, depth, k, allow_fuzzy=False)
        # exact-order: production output must match the sorted exhaustive reference exactly
        assert got == ref

def test_pruning_forces_dominance_prune_vs_reference():
    # Fully-connected hub-and-spoke: 4 distinct-priority parallel 2-hop paths
    # s -> p_i -> z, all EXPLICIT (same relationship-type tier), differentiated
    # only by confidence so their sort keys are strictly ordered with no ties.
    # max_depth=2 is exactly tight for every one of the 4 paths (hop(s)==2),
    # so the existing BFS admissible-depth-bound prune can NEVER fire here --
    # any prune observed is unambiguously a dominance prune. With max_paths=2
    # and 4 distinct-keyed paths, kept must fill with the 2 best and the
    # branches toward p3/p4 must be dominance-pruned to keep output correct.
    confidences = [("p1", 0.95), ("p2", 0.85), ("p3", 0.75), ("p4", 0.65)]
    legacy = {
        "tables": {t: {"columns": [{"name": "id", "primary_key": True}]}
                   for t in ["s", "p1", "p2", "p3", "p4", "z"]},
        "graph": {"nodes": ["s", "p1", "p2", "p3", "p4", "z"], "edges": []},
    }
    for p, conf in confidences:
        legacy["graph"]["edges"].append({
            "source": "s", "source_col": "id", "target": p, "target_col": "id",
            "type": "explicit", "confidence": conf})
        legacy["graph"]["edges"].append({
            "source": p, "source_col": "id", "target": "z", "target_col": "id",
            "type": "explicit", "confidence": conf})
    schema = from_legacy_schema(legacy, "postgres")

    result = find_join_paths(schema, "s", "z", max_depth=2, max_paths=2)
    ref = _exhaustive_reference_sorted(schema, "s", "z", 2, 2, allow_fuzzy=False)

    got = [c.tables for c in result.paths]
    assert got == ref == [["s", "p1", "z"], ["s", "p2", "z"]]
    # topology is depth-tight for every candidate path (BFS bound cannot fire) ->
    # a clean, unambiguous signal that dominance pruning actually fired
    assert result.branches_pruned >= 1
