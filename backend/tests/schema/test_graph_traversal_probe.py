from app.schema.schema_adapter import from_legacy_schema
from app.schema.graph_traversal import find_join_paths, JoinPathSearchResult, DEFAULT_JOIN_PATH_NODE_BUDGET
from app.schema.profiling import ProfileProbe


def _schema():
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


def test_probe_none_preserves_output():
    schema = _schema()
    before = find_join_paths(schema, "orders", "customers").paths
    after = find_join_paths(schema, "orders", "customers", probe=None).paths
    assert [c.model_dump() for c in before] == [c.model_dump() for c in after]


def test_probe_counts_dfs_and_paths():
    schema = _schema()
    probe = ProfileProbe()
    result = find_join_paths(schema, "orders", "customers", probe=probe)
    paths = result.paths
    assert paths
    assert probe.counts.get("dfs_visit", 0) >= 1
    assert probe.counts.get("path_recorded", 0) == len(paths)
    assert probe.counts.get("adjacency_edge", 0) >= 1


def test_returns_search_result_with_paths_and_stats():
    schema = _schema()
    result = find_join_paths(schema, "orders", "customers")
    assert isinstance(result, JoinPathSearchResult)
    assert [c.tables for c in result.paths] == [["orders", "customers"]]
    assert result.budget_truncated is False
    assert result.node_budget == DEFAULT_JOIN_PATH_NODE_BUDGET
    assert result.node_visits >= 1
    assert result.branches_pruned == 0


def test_bfs_bound_prunes_dead_branches():
    # star hub: center connects to many leaves; only leaf_target reaches target.
    legacy = {"tables": {
        "src": {"columns": [{"name": "id", "primary_key": True}, {"name": "hub_id"}],
                "foreign_keys": [{"column": "hub_id", "referenced_table": "hub",
                                  "referenced_column": "id", "type": "explicit"}]},
        "hub": {"columns": [{"name": "id", "primary_key": True}], "foreign_keys": []},
        "tgt": {"columns": [{"name": "id", "primary_key": True}, {"name": "hub_id"}],
                "foreign_keys": [{"column": "hub_id", "referenced_table": "hub",
                                  "referenced_column": "id", "type": "explicit"}]},
    }}
    # add 6 dead leaves off hub that cannot reach tgt within depth budget
    for i in range(6):
        legacy["tables"][f"leaf{i}"] = {
            "columns": [{"name": "id", "primary_key": True}, {"name": "hub_id"}],
            "foreign_keys": [{"column": "hub_id", "referenced_table": "hub",
                              "referenced_column": "id", "type": "explicit"}]}
    schema = from_legacy_schema(legacy, "postgres")
    probe = ProfileProbe()
    result = find_join_paths(schema, "src", "tgt", max_depth=2, probe=probe)
    assert [c.tables for c in result.paths] == [["src", "hub", "tgt"]]
    assert result.branches_pruned >= 1
    assert probe.counts.get("branches_pruned", 0) == result.branches_pruned
