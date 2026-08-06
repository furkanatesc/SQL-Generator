from app.schema.schema_adapter import from_legacy_schema
from app.schema.graph_traversal import find_join_paths, DEFAULT_JOIN_PATH_NODE_BUDGET
from app.schema.profiling import ProfileProbe

def _dense_hub_schema(n_leaves=40):
    """A hub every leaf references; enumerating leaf->hub->leaf paths blows up."""
    tables = {"hub": {"columns": [{"name": "id", "primary_key": True}], "foreign_keys": []}}
    for i in range(n_leaves):
        tables[f"t{i}"] = {
            "columns": [{"name": "id", "primary_key": True}, {"name": "hub_id"}],
            "foreign_keys": [{"column": "hub_id", "referenced_table": "hub",
                              "referenced_column": "id", "type": "explicit"}]}
    return from_legacy_schema({"tables": tables}, "postgres")

def test_budget_truncates_deterministically():
    schema = _dense_hub_schema()
    probe = ProfileProbe()
    result = find_join_paths(schema, "t0", "t1", max_depth=6, max_paths=5,
                             node_budget=25, probe=probe)
    assert result.budget_truncated is True
    assert result.node_visits <= 26  # stops just past the budget
    assert probe.counts.get("join_budget_truncated", 0) == 1
    # deterministic: same inputs -> same truncated output
    again = find_join_paths(schema, "t0", "t1", max_depth=6, max_paths=5, node_budget=25)
    assert [c.tables for c in result.paths] == [c.tables for c in again.paths]
    assert again.budget_truncated is True

def test_generous_default_never_truncates_small_schema():
    schema = _dense_hub_schema(n_leaves=5)
    result = find_join_paths(schema, "t0", "t1", max_depth=3)
    assert result.budget_truncated is False
    assert result.node_budget == DEFAULT_JOIN_PATH_NODE_BUDGET
