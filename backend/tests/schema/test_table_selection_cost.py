import json
from app.schema.table_selection_cost import (
    TableSelectionCostModel, DEFAULT_COST_MODEL, table_cost, fk_counts, from_config,
)
from app.schema.schema_adapter import from_legacy_schema


def test_default_weights_match_legacy_magic_numbers():
    m = DEFAULT_COST_MODEL
    assert (m.exact_table, m.singular_plural_table, m.table_token_overlap) == (100.0, 60.0, 40.0)
    assert (m.exact_column, m.column_token_overlap) == (80.0, 30.0)
    assert (m.explicit_neighbor, m.implicit_neighbor) == (20.0, 10.0)


def test_table_cost_is_base_plus_columns_plus_fks():
    m = TableSelectionCostModel(w_base=1.0, w_col=1.0, w_fk=2.0)
    assert table_cost(5, 3, m) == 1.0 + 5.0 + 6.0
    assert table_cost(0, 0, m) == 1.0


def test_fk_counts_counts_source_side_relationships():
    legacy = {"tables": {
        "users": {"columns": [{"name": "id", "primary_key": True}], "foreign_keys": []},
        "orders": {"columns": [{"name": "id", "primary_key": True}, {"name": "user_id"}],
                   "foreign_keys": [{"column": "user_id", "referenced_table": "users",
                                     "referenced_column": "id", "type": "explicit"}]},
    }}
    schema = from_legacy_schema(legacy, "postgres")
    counts = fk_counts(schema)
    assert counts.get("orders", 0) == 1   # orders owns the FK
    assert counts.get("users", 0) == 0    # users is only referenced


def test_from_config_none_or_invalid_returns_default():
    assert from_config(None) == DEFAULT_COST_MODEL
    assert from_config("") == DEFAULT_COST_MODEL
    assert from_config("{not json") == DEFAULT_COST_MODEL
    assert from_config(json.dumps([1, 2])) == DEFAULT_COST_MODEL  # not an object


def test_from_config_overrides_known_fields_only():
    raw = json.dumps({"exact_table": 200.0, "w_col": 2.0, "cost_budget": 50.0, "bogus": 1})
    m = from_config(raw)
    assert m.exact_table == 200.0 and m.w_col == 2.0 and m.cost_budget == 50.0
    assert m.singular_plural_table == DEFAULT_COST_MODEL.singular_plural_table  # untouched
