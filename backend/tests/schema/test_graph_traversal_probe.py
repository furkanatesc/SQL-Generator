from app.schema.schema_adapter import from_legacy_schema
from app.schema.graph_traversal import find_join_paths
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
    before = find_join_paths(schema, "orders", "customers")
    after = find_join_paths(schema, "orders", "customers", probe=None)
    assert [c.model_dump() for c in before] == [c.model_dump() for c in after]


def test_probe_counts_dfs_and_paths():
    schema = _schema()
    probe = ProfileProbe()
    paths = find_join_paths(schema, "orders", "customers", probe=probe)
    assert paths  # at least one path exists
    assert probe.counts.get("dfs_visit", 0) >= 1
    assert probe.counts.get("path_recorded", 0) == len(paths)
    assert probe.counts.get("adjacency_edge", 0) >= 1
