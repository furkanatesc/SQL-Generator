import pytest
import json
import os
from app.schema.schema_adapter import from_legacy_schema
from app.schema.schema_prompt_serializer import serialize_schema_for_prompt
from app.schema.graph_traversal import find_join_paths

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures", "schema")

def load_fixture(filename: str):
    with open(os.path.join(FIXTURES_DIR, filename), "r", encoding="utf-8") as f:
        data = json.load(f)
    return from_legacy_schema(data, dialect="unknown")

def test_schema_prompt_serialization_is_deterministic():
    schema = load_fixture("schema_prompt_basic_schema.json")
    first = serialize_schema_for_prompt(schema)
    second = serialize_schema_for_prompt(schema)
    assert first == second

def test_schema_prompt_serializes_tables_and_columns():
    schema = load_fixture("schema_prompt_basic_schema.json")
    context = serialize_schema_for_prompt(schema)
    
    assert "users" in context
    assert "- id INTEGER primary_key" in context
    assert "- email TEXT" in context

def test_schema_prompt_orders_relationships_by_trust_priority():
    schema = load_fixture("schema_prompt_relationship_priority_schema.json")
    context = serialize_schema_for_prompt(schema)
    
    explicit_idx = context.index("[explicit]")
    custom_idx = context.index("[custom]")
    implicit_idx = context.index("[implicit")
    fuzzy_idx = context.index("[implicit_fuzzy")
    
    assert explicit_idx < custom_idx < implicit_idx < fuzzy_idx

def test_schema_prompt_includes_confidence_and_reason_for_heuristic_relationships():
    schema = load_fixture("schema_prompt_relationship_priority_schema.json")
    context = serialize_schema_for_prompt(schema)
    
    assert "[implicit confidence=0.90 reason=singular_table_id_pattern]" in context
    assert "[implicit_fuzzy confidence=0.65 reason=fuzzy_prefix_to_table_match]" in context

def test_schema_prompt_respects_max_tables():
    schema = load_fixture("schema_prompt_token_budget_schema.json")
    context = serialize_schema_for_prompt(schema, max_tables=2)
    
    # Tables are lexical by default: audit_logs, orders, users
    # With max_tables=2, audit_logs and orders should be included, users should not be included.
    assert "audit_logs" in context
    assert "orders" in context
    assert "users" not in context

def test_schema_prompt_respects_max_columns_per_table():
    schema = load_fixture("schema_prompt_token_budget_schema.json")
    context = serialize_schema_for_prompt(schema, max_columns_per_table=2)
    
    # Helper to extract the users section
    def extract_table_section(ctx, table_name):
        lines = ctx.split("\n")
        try:
            start_idx = lines.index(table_name)
        except ValueError:
            return ""
        
        section_lines = []
        for line in lines[start_idx + 1:]:
            if line.strip() == "":
                break
            section_lines.append(line)
        return "\n".join(section_lines)
        
    users_section = extract_table_section(context, "users")
    assert "- id" in users_section
    assert "- email" in users_section
    assert "- created_at" not in users_section

def test_schema_prompt_serializes_join_paths():
    schema = load_fixture("schema_prompt_join_path_schema.json")
    paths = find_join_paths(schema, "orders", "users")
    
    context = serialize_schema_for_prompt(schema, join_paths=paths)
    
    assert "Join Paths:" in context
    assert "orders -> users" in context
    assert "[explicit] orders.user_id -> users.id" in context
