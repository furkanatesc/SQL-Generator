import json
from app.schema.table_selection_cost import (
    TableSelectionCostModel, DEFAULT_COST_MODEL, table_cost, fk_counts, from_config,
)
from app.schema.schema_adapter import from_legacy_schema


def test_default_weights_match_legacy_magic_numbers():
    m = DEFAULT_COST_MODEL
    assert (m.exact_table, m.singular_plural_table, m.table_token_overlap) == (100.0, 60.0, 40.0)
    assert (m.exact_column, m.column_token_overlap) == (80.0, 30.0)
    assert m.neighbor_base == 20.0


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


def test_neighbor_base_default_and_fuzzy_flag_default():
    m = DEFAULT_COST_MODEL
    assert m.neighbor_base == 20.0
    assert m.include_fuzzy_neighbors is False
    # old flat neighbor fields are gone
    assert not hasattr(m, "explicit_neighbor")
    assert not hasattr(m, "implicit_neighbor")


def test_neighbor_benefit_multiplies_base_by_confidence():
    from app.schema.table_selection_cost import neighbor_benefit
    m = TableSelectionCostModel(neighbor_base=20.0)
    assert neighbor_benefit(None, m) == 20.0     # explicit/custom -> 1.0
    assert neighbor_benefit(1.0, m) == 20.0
    assert neighbor_benefit(0.9, m) == 18.0
    assert neighbor_benefit(0.6, m) == 12.0


def test_from_config_accepts_neighbor_base_and_fuzzy_bool_and_drops_old_keys():
    raw = json.dumps({"neighbor_base": 30.0, "include_fuzzy_neighbors": True,
                      "explicit_neighbor": 999, "implicit_neighbor": 999})
    m = from_config(raw)
    assert m.neighbor_base == 30.0
    assert m.include_fuzzy_neighbors is True
    # old keys silently ignored (not accepted, no crash)
    assert not hasattr(m, "explicit_neighbor")


def test_from_config_ignores_non_bool_fuzzy_flag():
    m = from_config(json.dumps({"include_fuzzy_neighbors": "yes"}))
    assert m.include_fuzzy_neighbors is False  # non-bool ignored -> default
