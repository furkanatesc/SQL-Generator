import pytest
from app.schema.schema_contract import DatabaseSchema, TableSchema, ColumnSchema, RelationshipSchema, RelationshipType, SchemaGraph
from app.schema.schema_context_selector import select_schema_context
from app.schema.schema_prompt_serializer import serialize_selection_for_prompt

@pytest.fixture
def sample_schema():
    return DatabaseSchema(
        dialect="postgres",
        tables=[
            TableSchema(
                name="audit_logs",
                columns=[ColumnSchema(name="id", primary_key=True), ColumnSchema(name="log_text")]
            ),
            TableSchema(
                name="customers",
                columns=[ColumnSchema(name="id", primary_key=True), ColumnSchema(name="name")]
            ),
            TableSchema(
                name="orders",
                columns=[ColumnSchema(name="id", primary_key=True), ColumnSchema(name="customer_id")]
            ),
            TableSchema(
                name="payments",
                columns=[ColumnSchema(name="id", primary_key=True), ColumnSchema(name="order_id"), ColumnSchema(name="amount")]
            ),
            TableSchema(
                name="products",
                columns=[ColumnSchema(name="id", primary_key=True), ColumnSchema(name="name")]
            ),
            TableSchema(
                name="users",
                columns=[ColumnSchema(name="id", primary_key=True), ColumnSchema(name="username")]
            )
        ],
        relationships=[
            RelationshipSchema(
                source_table="orders", source_column="customer_id",
                target_table="customers", target_column="id",
                relationship_type=RelationshipType.EXPLICIT
            ),
            RelationshipSchema(
                source_table="payments", source_column="order_id",
                target_table="orders", target_column="id",
                relationship_type=RelationshipType.EXPLICIT
            )
        ],
        graph=SchemaGraph(
            nodes=["audit_logs", "customers", "orders", "payments", "products", "users"],
            edges=[
                RelationshipSchema(
                    source_table="orders", source_column="customer_id",
                    target_table="customers", target_column="id",
                    relationship_type=RelationshipType.EXPLICIT
                ),
                RelationshipSchema(
                    source_table="payments", source_column="order_id",
                    target_table="orders", target_column="id",
                    relationship_type=RelationshipType.EXPLICIT
                )
            ]
        )
    )

def get_serialized_prompt(schema, selection):
    return serialize_selection_for_prompt(schema, selection)

def test_integration_selected_tables_only(sample_schema):
    question = "Show orders with customer names"
    selection = select_schema_context(sample_schema, question, max_tables=2)
    prompt = get_serialized_prompt(sample_schema, selection)
    
    assert "customers" in prompt.split("Tables:")[1]
    assert "orders" in prompt.split("Tables:")[1]
    assert "audit_logs" not in prompt.split("Tables:")[1]
    assert "products" not in prompt.split("Tables:")[1]
    assert "payments" not in prompt.split("Tables:")[1]

def test_prompt_relationships_include_only_selected_table_fks(sample_schema):
    question = "Show orders with customer names"
    selection = select_schema_context(sample_schema, question, max_tables=2)
    prompt = get_serialized_prompt(sample_schema, selection)
    
    assert "orders.customer_id -> customers.id" in prompt
    assert "payments.order_id -> orders.id" not in prompt
    assert "customers.id -> orders.customer_id" not in prompt  # check direction is not reversed

def test_join_path_tables_are_included_in_prompt_context(sample_schema):
    question = "Show payments for each customer name"
    selection = select_schema_context(sample_schema, question, max_tables=3)
    prompt = get_serialized_prompt(sample_schema, selection)
    
    assert "payments" in prompt.split("Relationships:")[0]
    assert "customers" in prompt.split("Relationships:")[0]
    
    assert "Join Paths:" in prompt
    
    # Check that intermediate table (orders) is in the tables block
    tables_block = prompt.split("Relationships:")[0]
    assert "\norders\n" in tables_block
    assert "  - id " in tables_block.split("\norders\n")[1]

def test_fallback_uses_at_most_five_tables(sample_schema):
    question = "unknown_term_that_matches_nothing xyz123"
    selection = select_schema_context(sample_schema, question)
    prompt = get_serialized_prompt(sample_schema, selection)
    
    assert prompt.count("  - id") <= 5
    assert selection.fallback_used is True
    assert selection.fallback_strategy == "deterministic_bounded_fallback"

def test_fallback_respects_max_tables_lower_than_five(sample_schema):
    question = "unknown_term_that_matches_nothing xyz123"
    selection = select_schema_context(sample_schema, question, max_tables=3)
    assert len(selection.focus_tables) == 3
    assert selection.fallback_limit == 3

def test_fallback_is_deterministic(sample_schema):
    question = "unknown_term_that_matches_nothing xyz123"
    selection1 = select_schema_context(sample_schema, question)
    prompt1 = get_serialized_prompt(sample_schema, selection1)
    
    selection2 = select_schema_context(sample_schema, question)
    prompt2 = get_serialized_prompt(sample_schema, selection2)
    
    assert prompt1 == prompt2

def test_fallback_is_traced(sample_schema):
    question = "unknown_term_that_matches_nothing xyz123"
    selection = select_schema_context(sample_schema, question)
    
    trace_fragment = {
        "schema_context_selection": {
            "fallback_used": selection.fallback_used,
            "fallback_strategy": selection.fallback_strategy,
            "selector_version": "deterministic_v1"
        }
    }
    
    assert trace_fragment["schema_context_selection"]["fallback_used"] is True
    assert trace_fragment["schema_context_selection"]["fallback_strategy"] == "deterministic_bounded_fallback"
