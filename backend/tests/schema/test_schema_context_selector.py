import json
import os
from app.schema.schema_adapter import from_legacy_schema
from app.schema.schema_context_selector import select_schema_context
from app.schema.table_selection_cost import TableSelectionCostModel, DEFAULT_COST_MODEL

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

def test_selection_propagates_budget_truncation():
    # A single-hub star schema does NOT force truncation here: the selector's
    # find_join_paths call uses a fixed max_depth=3, and BFS hop-distance pruning
    # cuts off all non-productive star branches before they are ever visited
    # (verified empirically), so no amount of hub fan-out trips the budget.
    # A many-to-many junction/bipartite pattern (two anchor tables joined
    # through many link tables, each equally a shortest path) defeats that
    # pruning because every link table sits on a genuine shortest path and
    # must be visited, which is exactly the "join path explosion" this
    # sprint targets.
    tables = {
        "left": {"columns": [{"name": "id", "primary_key": True}], "foreign_keys": []},
        "right": {"columns": [{"name": "id", "primary_key": True}], "foreign_keys": []},
    }
    for i in range(20):
        tables[f"link{i}"] = {
            "columns": [{"name": "id", "primary_key": True}, {"name": "left_id"}, {"name": "right_id"}],
            "foreign_keys": [
                {"column": "left_id", "referenced_table": "left",
                 "referenced_column": "id", "type": "explicit"},
                {"column": "right_id", "referenced_table": "right",
                 "referenced_column": "id", "type": "explicit"},
            ]}
    schema = from_legacy_schema({"tables": tables}, "postgres")
    sel = select_schema_context(schema, "left right", node_budget=15)
    assert sel.join_search_truncated is True

def test_selection_not_truncated_by_default():
    schema = from_legacy_schema({"tables": {
        "users": {"columns": [{"name": "id", "primary_key": True}], "foreign_keys": []},
        "orders": {"columns": [{"name": "id", "primary_key": True}, {"name": "user_id"}],
                   "foreign_keys": [{"column": "user_id", "referenced_table": "users",
                                     "referenced_column": "id", "type": "explicit"}]}}}, "postgres")
    sel = select_schema_context(schema, "orders users")
    assert sel.join_search_truncated is False


# --- Sprint 28.3: benefit-density budget selection ---

def _two_table_schema():
    legacy = {"tables": {
        "orders": {"columns": [{"name": "id", "primary_key": True}, {"name": "customer_id"}],
                   "foreign_keys": [{"column": "customer_id", "referenced_table": "customers",
                                     "referenced_column": "id", "type": "explicit"}]},
        "customers": {"columns": [{"name": "id", "primary_key": True}, {"name": "name"}],
                      "foreign_keys": []},
    }}
    return from_legacy_schema(legacy, "postgres")

def test_selected_tables_carry_cost_and_selection_reports_total():
    schema = _two_table_schema()
    sel = select_schema_context(schema, "orders customers")
    assert all(st.cost > 0 for st in sel.selected_tables)
    assert sel.total_cost == sum(st.cost for st in sel.selected_tables)
    assert sel.cost_budget == DEFAULT_COST_MODEL.cost_budget
    assert sel.budget_exhausted is False  # tiny schema fits the default budget

def _tight_budget_schema():
    # NOTE: the brief's original scenario used "orders customers" against a
    # two-table schema where BOTH tables are exact-table-matches, so both get
    # force-included regardless of budget (budget_exhausted would stay False
    # incorrectly). To genuinely exercise budget binding we need two
    # NON-exact-match (here: singular/plural token) candidates with DIFFERENT
    # costs, so the tight budget can afford the cheaper/denser one but not
    # both.
    #
    # "order_items" tokenizes to {"order", "items"} -> singularized
    # {"order", "item"}; "invoice_items" tokenizes to {"invoice", "items"} ->
    # singularized {"invoice", "item"}. Question "items" singularizes to
    # {"item"}, which intersects both tables' singular token sets, so BOTH
    # score via singular_plural_table_match (60.0 each) -- NEITHER is an
    # exact_table_match (the literal string "order_items"/"invoice_items"
    # is not a substring of "items"), so neither is force-included.
    #
    # Costs (w_base=1.0, w_col=1.0, w_fk=0.0 in DEFAULT_COST_MODEL):
    #   order_items:   1 + 3 columns (id, order_id, qty) = 4.0
    #   invoice_items: 1 + 2 columns (id, invoice_id)     = 3.0
    # Benefit is tied (60.0 each), so density favors invoice_items
    # (60/3=20.0) over order_items (60/4=15.0).
    legacy = {"tables": {
        "order_items": {"columns": [{"name": "id", "primary_key": True},
                                     {"name": "order_id"}, {"name": "qty"}],
                         "foreign_keys": []},
        "invoice_items": {"columns": [{"name": "id", "primary_key": True},
                                       {"name": "invoice_id"}],
                           "foreign_keys": []},
    }}
    return from_legacy_schema(legacy, "postgres")

def test_tight_budget_prefers_small_relevant_table_and_flags_exhaustion():
    # invoice_items (cost 3.0, density 20.0) and order_items (cost 4.0,
    # density 15.0) tie on benefit (60.0, singular/plural match on "items")
    # but neither is an exact match, so neither is force-included. A budget
    # of 3.5 can afford only the denser/cheaper invoice_items.
    schema = _tight_budget_schema()
    model = TableSelectionCostModel(cost_budget=3.5)
    sel = select_schema_context(schema, "items", cost_model=model)
    assert [st.table_name for st in sel.selected_tables] == ["invoice_items"]
    assert sel.total_cost == 3.0
    assert sel.total_cost <= 3.5
    assert sel.budget_exhausted is True

def test_exact_match_focus_always_included_even_if_expensive():
    schema = _two_table_schema()
    # budget below any single table cost; exact-match focus must still appear
    model = TableSelectionCostModel(cost_budget=0.0)
    sel = select_schema_context(schema, "orders")  # 'orders' is an exact table match
    # 'orders' forced in despite zero budget
    assert "orders" in [st.table_name for st in sel.selected_tables]


# --- Sprint 28.3.1 Task 5 (TECH-DEBT §12.16): fallback regime must not
# co-report budget_exhausted=True alongside fallback_used=True ---

def test_fallback_regime_does_not_report_budget_exhausted():
    # Single table "order_items" tokenizes to {"order", "items"} ->
    # singularized {"order", "item"}. Question "items" singularizes to
    # {"item"}, which intersects that set, so the table scores via
    # singular_plural_table_match (NOT exact_table_match: the literal string
    # "order_items" is not a substring of "items"). Because it is not an
    # exact match, it is NOT force-included and instead goes through the
    # budget-gated `rest` path.
    #
    # Cost (w_base=1.0, w_col=1.0, w_fk=0.0): 1 + 10 columns = 11.0, which
    # exceeds the tiny injected cost_budget=5.0. The `rest` loop therefore
    # skips it and sets budget_exhausted=True internally, leaving
    # selected_tables empty -> the deterministic bounded fallback fires.
    #
    # The fallback is a distinct, bounded (<=5 table) safety net, not the
    # budget-gated regime, so it must report budget_exhausted=False even
    # though the (now-irrelevant) budget-gated path was exhausted first.
    legacy = {"tables": {
        "order_items": {
            "columns": [{"name": "id", "primary_key": True}] +
                       [{"name": f"c{i}"} for i in range(9)],  # 10 cols -> cost 11.0
            "foreign_keys": []},
    }}
    schema = from_legacy_schema(legacy, "postgres")
    model = TableSelectionCostModel(cost_budget=5.0)

    sel = select_schema_context(schema, "items", cost_model=model)

    assert sel.fallback_used is True
    assert sel.budget_exhausted is False
    assert [st.table_name for st in sel.selected_tables] == ["order_items"]
    assert sel.selected_tables[0].reasons == ["fallback"]


# --- Sprint 28.4: confidence-weighted neighbor expansion + fuzzy opt-in ---

def _schema_with_implicit_neighbor():
    # 'orders' token-matches the question; 'customers' is an IMPLICIT neighbor (conf 0.6).
    legacy = {"tables": {
        "orders": {"columns": [{"name": "id", "primary_key": True}, {"name": "customer_id"}],
                   "foreign_keys": []},
        "customers": {"columns": [{"name": "id", "primary_key": True}], "foreign_keys": []},
    }, "graph": {"nodes": ["orders", "customers"], "edges": [
        {"source": "orders", "source_col": "customer_id", "target": "customers",
         "target_col": "id", "type": "implicit", "confidence": 0.6}]}}
    return from_legacy_schema(legacy, "postgres")

def test_implicit_neighbor_benefit_scaled_by_confidence():
    schema = _schema_with_implicit_neighbor()
    sel = select_schema_context(schema, "orders")  # 'orders' exact-matches
    by_name = {st.table_name: st for st in sel.selected_tables}
    assert "customers" in by_name
    # implicit neighbor benefit = neighbor_base(20) * confidence(0.6) = 12.0
    assert by_name["customers"].score == 12.0

def test_explicit_neighbor_benefit_is_full_base():
    legacy = {"tables": {
        "orders": {"columns": [{"name": "id", "primary_key": True}, {"name": "customer_id"}],
                   "foreign_keys": [{"column": "customer_id", "referenced_table": "customers",
                                     "referenced_column": "id", "type": "explicit"}]},
        "customers": {"columns": [{"name": "id", "primary_key": True}], "foreign_keys": []},
    }}
    schema = from_legacy_schema(legacy, "postgres")
    sel = select_schema_context(schema, "orders")
    by_name = {st.table_name: st for st in sel.selected_tables}
    # explicit neighbor conf None -> 1.0 -> 20.0 (unchanged from old explicit_neighbor)
    assert by_name["customers"].score == 20.0

def test_fuzzy_neighbor_excluded_by_default_included_when_enabled():
    legacy = {"tables": {
        "orders": {"columns": [{"name": "id", "primary_key": True}, {"name": "cust"}],
                   "foreign_keys": []},
        "customers": {"columns": [{"name": "id", "primary_key": True}], "foreign_keys": []},
    }, "graph": {"nodes": ["orders", "customers"], "edges": [
        {"source": "orders", "source_col": "cust", "target": "customers",
         "target_col": "id", "type": "implicit_fuzzy", "confidence": 0.7}]}}
    schema = from_legacy_schema(legacy, "postgres")
    default_sel = select_schema_context(schema, "orders")
    assert "customers" not in [st.table_name for st in default_sel.selected_tables]
    enabled = TableSelectionCostModel(include_fuzzy_neighbors=True)
    on_sel = select_schema_context(schema, "orders", cost_model=enabled)
    by_name = {st.table_name: st for st in on_sel.selected_tables}
    assert "customers" in by_name
    assert by_name["customers"].score == 20.0 * 0.7  # 14.0
