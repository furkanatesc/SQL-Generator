import json
import os
from app.schema.schema_adapter import from_legacy_schema
from app.schema.schema_context_selector import select_schema_context

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures", "schema")

def load_fixture(filename: str):
    with open(os.path.join(FIXTURES_DIR, filename), "r", encoding="utf-8") as f:
        data = json.load(f)
    return from_legacy_schema(data, dialect="unknown")

def test_schema_context_selection_is_deterministic():
    schema = load_fixture("context_selection_basic_schema.json")
    
    first = select_schema_context(schema, "show orders by user")
    second = select_schema_context(schema, "show orders by user")
    
    assert first == second

def test_schema_context_selects_exact_table_match():
    schema = load_fixture("context_selection_basic_schema.json")
    
    selection = select_schema_context(schema, "show all orders")
    
    assert selection.focus_tables[0] == "orders"

def test_schema_context_selects_table_by_column_match():
    schema = load_fixture("context_selection_basic_schema.json")
    
    selection = select_schema_context(schema, "show total amount")
    
    assert "orders" in selection.focus_tables

def test_schema_context_adds_explicit_relationship_neighbor():
    schema = load_fixture("context_selection_relationship_schema.json")
    
    selection = select_schema_context(schema, "show orders by user")
    
    assert "orders" in selection.focus_tables
    assert "users" in [t.table_name for t in selection.selected_tables]

def test_schema_context_does_not_expand_fuzzy_relationship_by_default():
    schema = load_fixture("context_selection_ambiguous_schema.json")
    
    # Query mentions employees, but does not mention department.
    # Therefore departments table should only be added if relationship expansion permits it.
    selection = select_schema_context(schema, "show all employees")
    
    # "departments" should NOT be selected because the implicit_fuzzy edge shouldn't expand
    assert "departments" not in selection.focus_tables

def test_schema_context_respects_max_tables():
    schema = load_fixture("context_selection_token_budget_schema.json")
    
    selection = select_schema_context(
        schema, 
        "show users orders payments invoices audit logs",
        max_tables=3
    )
    
    assert len(selection.selected_tables) == 3
    assert len(selection.focus_tables) == 3

def test_schema_context_returns_join_paths_for_selected_tables():
    schema = load_fixture("context_selection_relationship_schema.json")
    
    selection = select_schema_context(schema, "show orders by user")
    
    assert any(set(path.tables) == {"orders", "users"} for path in selection.join_paths)
