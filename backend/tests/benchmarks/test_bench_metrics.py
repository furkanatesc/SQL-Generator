from benchmarks import bench_metrics as m
from app.schema.schema_adapter import from_legacy_schema
from app.schema.schema_contract import RelationshipSchema, RelationshipType


def _mini_schema():
    legacy = {
        "tables": {
            "customers": {"columns": [{"name": "id", "primary_key": True}], "foreign_keys": []},
            "orders": {
                "columns": [{"name": "id", "primary_key": True}, {"name": "customer_id"}],
                "foreign_keys": [{"column": "customer_id", "referenced_table": "customers",
                                  "referenced_column": "id", "type": "explicit"}],
            },
        }
    }
    return from_legacy_schema(legacy, "postgres")


def test_validation_metrics():
    d = m.derive_validation_metrics(_mini_schema())
    assert d == {"tables": 2, "columns_total": 3, "relationships_validated": 1, "valid": 1}


def test_join_path_metrics_counts_paths_and_edges():
    class _Cand:
        def __init__(self, edges):
            self.edges = edges
    results = [
        ("orders", "customers", [_Cand(edges=["e1"])]),
        ("customers", "orders", []),
    ]
    d = m.derive_join_path_metrics(results, adjacency_edges=1)
    assert d == {"pairs_evaluated": 2, "paths_found_total": 1, "path_edges_total": 1,
                 "pairs_with_path": 1, "adjacency_edges": 1}


def test_implicit_fk_metrics_buckets_by_rule():
    def _rel(rule):
        return RelationshipSchema(source_table="a", source_column="x", target_table="b",
                                  target_column="id", relationship_type=RelationshipType.IMPLICIT,
                                  raw={"rule": rule})
    rels = [_rel("singular_table_id_pattern"), _rel("fuzzy_prefix_match"),
            _rel("exact_column_match"), _rel("singular_table_id_pattern")]
    d = m.derive_implicit_fk_metrics(rels)
    assert d == {"implicit_rels_found": 4, "rule1_singular_id": 2,
                 "rule2_fuzzy": 1, "rule3_exact": 1, "other": 0}


def test_implicit_fk_metrics_other_bucket_and_missing_raw():
    def _rel_with_raw(raw):
        return RelationshipSchema(source_table="a", source_column="x", target_table="b",
                                  target_column="id", relationship_type=RelationshipType.IMPLICIT,
                                  raw=raw)
    rels = [_rel_with_raw({"rule": "some_unknown_rule"}), _rel_with_raw({})]
    d = m.derive_implicit_fk_metrics(rels)
    assert d == {"implicit_rels_found": 2, "rule1_singular_id": 0,
                 "rule2_fuzzy": 0, "rule3_exact": 0, "other": 2}


def test_selection_metrics():
    class _Sel:
        def __init__(self, focus, sel, jp, fb):
            self.focus_tables = focus
            self.selected_tables = sel
            self.join_paths = jp
            self.fallback_used = fb
    results = [_Sel(["a"], ["a", "b"], ["p"], False), _Sel([], ["c"], [], True)]
    d = m.derive_selection_metrics(results)
    assert d == {"questions_evaluated": 2, "focus_tables_total": 1,
                 "selected_tables_total": 3, "join_paths_total": 1, "fallback_used_count": 1}


def test_graph_backend_metrics():
    sp_results = [["a", "b", "c"], [], ["a", "b"]]
    d = m.derive_graph_backend_metrics(graph_nodes=10, graph_edges=12, sp_results=sp_results)
    assert d == {"graph_nodes": 10, "graph_edges": 12, "sp_pairs_evaluated": 3,
                 "sp_pairs_with_path": 2, "sp_total_path_len": 5}


def test_schema_version_is_v3():
    from benchmarks.bench_contract import BENCHMARK_SCHEMA_VERSION
    assert BENCHMARK_SCHEMA_VERSION == "large_schema_benchmark_v3"
