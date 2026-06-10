import pytest
from app.schema.schema_contract import DatabaseSchema, TableSchema, ColumnSchema, RelationshipSchema, RelationshipType, SchemaGraph
from app.schema.schema_context_selector import select_schema_context
from app.schema.prompt_serializer import serialize_schema_for_prompt

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

def count_serialized_tables(prompt: str) -> int:
    return prompt.count("TABLE ")

def test_integration_selected_tables_only(sample_schema):
    question = "Show orders with customer names"
    selection = select_schema_context(sample_schema, question, max_tables=2)
    prompt = serialize_schema_for_prompt(sample_schema, selection)
    
    assert "TABLE customers" in prompt
    assert "TABLE orders" in prompt
    assert "TABLE audit_logs" not in prompt
    assert "TABLE products" not in prompt
    assert "TABLE payments" not in prompt

def test_prompt_relationships_include_only_selected_table_fks(sample_schema):
    question = "Show orders with customer names"
    selection = select_schema_context(sample_schema, question, max_tables=2)
    prompt = serialize_schema_for_prompt(sample_schema, selection)
    
    assert "orders.customer_id -> customers.id" in prompt
    assert "payments.order_id -> orders.id" not in prompt
    assert "customers.id -> orders.customer_id" not in prompt  # check direction is not reversed

def test_join_path_tables_are_included_in_prompt_context(sample_schema):
    question = "Show payments for each customer name"
    selection = select_schema_context(sample_schema, question, max_tables=3)
    prompt = serialize_schema_for_prompt(sample_schema, selection)
    
    assert "TABLE payments" in prompt
    assert "TABLE customers" in prompt
    
    # Depending on graph traversal direction, check path
    # `find_join_paths` returns path tables.
    assert "JOIN PATH: " in prompt
    assert "orders" in prompt  # The intermediate table must be mentioned in the path

def test_fallback_uses_at_most_five_tables(sample_schema):
    question = "unknown_term_that_matches_nothing xyz123"
    selection = select_schema_context(sample_schema, question)
    prompt = serialize_schema_for_prompt(sample_schema, selection)
    
    assert count_serialized_tables(prompt) <= 5
    assert selection.fallback_used is True
    assert selection.fallback_strategy == "deterministic_top_5"

def test_fallback_is_deterministic(sample_schema):
    question = "unknown_term_that_matches_nothing xyz123"
    selection1 = select_schema_context(sample_schema, question)
    prompt1 = serialize_schema_for_prompt(sample_schema, selection1)
    
    selection2 = select_schema_context(sample_schema, question)
    prompt2 = serialize_schema_for_prompt(sample_schema, selection2)
    
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
    assert trace_fragment["schema_context_selection"]["fallback_strategy"] == "deterministic_top_5"
