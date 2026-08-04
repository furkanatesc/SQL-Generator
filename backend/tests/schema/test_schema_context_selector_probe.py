# backend/tests/schema/test_schema_context_selector_probe.py
from app.schema.schema_adapter import from_legacy_schema
from app.schema.schema_context_selector import select_schema_context
from app.schema.profiling import ProfileProbe


def _schema():
    legacy = {
        "tables": {
            "customers": {"columns": [{"name": "id", "primary_key": True},
                                      {"name": "name"}], "foreign_keys": []},
            "orders": {"columns": [{"name": "id", "primary_key": True},
                                   {"name": "customer_id"}],
                       "foreign_keys": [{"column": "customer_id", "referenced_table": "customers",
                                         "referenced_column": "id", "type": "explicit"}]},
        }
    }
    return from_legacy_schema(legacy, "postgres")


def test_probe_none_preserves_output():
    schema = _schema()
    before = select_schema_context(schema, "list all customers with their orders")
    after = select_schema_context(schema, "list all customers with their orders", probe=None)
    assert before.model_dump() == after.model_dump()


def test_probe_counts_scans():
    schema = _schema()
    probe = ProfileProbe()
    select_schema_context(schema, "list all customers with their orders", probe=probe)
    assert probe.counts.get("table_scan", 0) == 2          # two tables scanned
    assert probe.counts.get("column_scan", 0) == 4         # 2 + 2 columns
