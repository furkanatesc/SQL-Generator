import pytest
import json
import os
from app.schema.schema_adapter import from_legacy_schema
from app.schema.schema_contract import RelationshipType

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures", "schema")

def load_fixture(filename: str) -> dict:
    with open(os.path.join(FIXTURES_DIR, filename), "r", encoding="utf-8") as f:
        return json.load(f)

def semantic_edges(schema) -> set:
    return {
        (rel.source_table, rel.source_column, rel.target_table, rel.target_column, rel.relationship_type)
        for rel in schema.relationships
    }

def test_sqlite_fk_direction_is_child_to_parent():
    fixture = load_fixture("sqlite_fk_schema.json")
    schema = from_legacy_schema(fixture, dialect="sqlite")

    assert len(schema.relationships) == 1
    rel = schema.relationships[0]

    assert rel.source_table == "orders"
    assert rel.source_column == "user_id"
    assert rel.target_table == "users"
    assert rel.target_column == "id"
    assert rel.relationship_type == RelationshipType.EXPLICIT

def test_postgres_fk_matches_relationship_contract():
    fixture = load_fixture("postgres_fk_schema.json")
    schema = from_legacy_schema(fixture, dialect="postgres")

    assert semantic_edges(schema) == {
        ("orders", "user_id", "users", "id", RelationshipType.EXPLICIT)
    }

def test_oracle_fk_preserves_identifier_case_and_direction():
    fixture = load_fixture("oracle_fk_schema.json")
    schema = from_legacy_schema(fixture, dialect="oracle")

    assert semantic_edges(schema) == {
        ("ORDERS", "USER_ID", "USERS", "ID", RelationshipType.EXPLICIT)
    }

def test_fk_rejects_source_column_not_in_source_table():
    fixture = load_fixture("invalid_fk_source_column_schema.json")
    with pytest.raises(ValueError, match="Relationship source_column 'invalid_user_id' not found in table 'orders'"):
        from_legacy_schema(fixture)

def test_composite_fk_components_preserve_constraint_group_in_raw():
    fixture = load_fixture("composite_fk_schema.json")
    schema = from_legacy_schema(fixture, dialect="postgres")

    edges = schema.relationships
    assert len(edges) == 2

    assert edges[0].raw["constraint_name"] == "fk_order_item_order"
    assert edges[0].raw["composite_group"] == "fk_order_item_order"
    assert edges[0].raw["ordinal"] == 1

    assert edges[1].raw["constraint_name"] == "fk_order_item_order"
    assert edges[1].raw["composite_group"] == "fk_order_item_order"
    assert edges[1].raw["ordinal"] == 2
