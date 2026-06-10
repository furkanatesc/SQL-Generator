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

def extract_section(context: str, start_marker: str, end_marker: str = None) -> str:
    lines = context.split("\n")
    try:
        start_idx = lines.index(start_marker)
    except ValueError:
        return ""
        
    end_idx = len(lines)
    if end_marker:
        try:
            end_idx = lines.index(end_marker, start_idx + 1)
        except ValueError:
            pass
            
    return "\n".join(lines[start_idx:end_idx])

def extract_table_section(context: str, table_name: str) -> str:
    lines = context.split("\n")
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

def test_schema_prompt_serialization_is_deterministic():
    schema = load_fixture("schema_prompt_basic_schema.json")
    first = serialize_schema_for_prompt(schema)
    second = serialize_schema_for_prompt(schema)
    assert first == second

def test_schema_prompt_serializes_tables_and_columns():
    schema = load_fixture("schema_prompt_basic_schema.json")
    context = serialize_schema_for_prompt(schema)
    
    tables_section = extract_section(context, "Tables:", "Relationships:")
    assert "users" in tables_section
    
    users_section = extract_table_section(context, "users")
    assert "- id INTEGER primary_key" in users_section
    assert "- email TEXT" in users_section

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
    
    tables_section = extract_section(context, "Tables:", "Relationships:")
    assert "audit_logs" in tables_section
    assert "orders" in tables_section
    assert "users" not in tables_section

def test_schema_prompt_respects_max_columns_per_table():
    schema = load_fixture("schema_prompt_token_budget_schema.json")
    context = serialize_schema_for_prompt(schema, max_columns_per_table=2)
        
    users_section = extract_table_section(context, "users")
    assert "- id" in users_section
    assert "- email" in users_section
    assert "- created_at" not in users_section

def test_schema_prompt_serializes_join_paths():
    schema = load_fixture("schema_prompt_join_path_schema.json")
    paths = find_join_paths(schema, "orders", "users")
    
    context = serialize_schema_for_prompt(schema, join_paths=paths)
    
    join_paths_section = extract_section(context, "Join Paths:")
    assert "orders -> users" in join_paths_section
    assert "[explicit] orders.user_id -> users.id" in join_paths_section

def test_schema_prompt_preserves_relationship_columns_when_column_limit_is_low():
    schema = load_fixture("schema_prompt_relationship_column_limit_schema.json")
    context = serialize_schema_for_prompt(schema, max_columns_per_table=1)

    orders_section = extract_table_section(context, "orders")

    # Limit is 1, but PK and required column should both be included
    assert "- id INTEGER primary_key" in orders_section
    assert "- user_id INTEGER" in orders_section
    
    # And relationships should still show the explicit relationship
    assert "[explicit] orders.user_id -> users.id" in context

def test_schema_prompt_preserves_join_path_columns_when_column_limit_is_low():
    schema = load_fixture("schema_prompt_relationship_column_limit_schema.json")
    # Even if relationships are omitted globally, join_path columns should be forced
    paths = find_join_paths(schema, "orders", "users")
    context = serialize_schema_for_prompt(schema, join_paths=paths, max_columns_per_table=1, include_relationships=False)

    orders_section = extract_table_section(context, "orders")
    assert "- id INTEGER primary_key" in orders_section
    assert "- user_id INTEGER" in orders_section

def test_schema_prompt_can_exclude_confidence_and_reason():
    schema = load_fixture("schema_prompt_relationship_priority_schema.json")
    context = serialize_schema_for_prompt(schema, include_confidence=False)
    
    rels_section = extract_section(context, "Relationships:")
    assert "[implicit] payments.user_id -> users.id" in rels_section
    assert "confidence=" not in rels_section
    assert "reason=" not in rels_section

def test_schema_prompt_can_exclude_relationships_section():
    schema = load_fixture("schema_prompt_relationship_priority_schema.json")
    context = serialize_schema_for_prompt(schema, include_relationships=False)
    
    assert "Relationships:" not in context
