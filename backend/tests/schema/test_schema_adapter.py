import pytest
import json
import os
from app.schema.schema_adapter import from_legacy_schema, to_legacy_dict

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures", "schema")

def load_fixture(filename: str) -> dict:
    with open(os.path.join(FIXTURES_DIR, filename), "r", encoding="utf-8") as f:
        return json.load(f)

def test_legacy_adapter_preserves_tables_columns_and_relationships():
    raw = {
        "tables": {
            "users": {
                "columns": [
                    {"name": "id", "type": "INTEGER", "primary_key": True},
                    {"name": "email", "type": "TEXT", "nullable": False},
                ]
            },
            "orders": {
                "columns": [
                    {"name": "id", "type": "INTEGER", "primary_key": True},
                    {"name": "user_id", "type": "INTEGER"},
                ]
            },
        },
        "graph": {
            "nodes": ["users", "orders"],
            "edges": [
                {
                    "source": "orders",
                    "target": "users",
                    "source_col": "user_id",
                    "target_col": "id",
                    "type": "explicit",
                }
            ]
        }
    }

    typed = from_legacy_schema(raw, dialect="sqlite")

    assert typed.dialect == "sqlite"
    assert [t.name for t in typed.tables] == ["users", "orders"]
    
    orders_table = next(t for t in typed.tables if t.name == "orders")
    assert [c.name for c in orders_table.columns] == ["id", "user_id"]
    
    assert len(typed.relationships) == 1
    rel = typed.relationships[0]
    assert rel.source_table == "orders"
    assert rel.target_table == "users"
    assert rel.source_column == "user_id"
    assert rel.target_column == "id"

def test_legacy_roundtrip_does_not_drop_core_schema_information_sqlite():
    raw_schema_fixture = load_fixture("sqlite_basic_schema.json")
    
    typed = from_legacy_schema(raw_schema_fixture, dialect="sqlite")
    legacy = to_legacy_dict(typed)

    assert "users" in legacy["tables"]
    assert legacy["tables"]["users"]["columns"][0]["name"] == "id"
    
    edges = legacy.get("graph", {}).get("edges", [])
    assert len(edges) > 0
    assert edges[0]["source"] == "orders"
    assert edges[0]["target"] == "users"
    
    # Original dict format matching
    assert legacy["tables"]["users"]["columns"][0]["primary_key"] is True

def test_legacy_roundtrip_does_not_drop_core_schema_information_postgres():
    raw_schema_fixture = load_fixture("postgres_basic_schema.json")
    
    typed = from_legacy_schema(raw_schema_fixture, dialect="postgres")
    legacy = to_legacy_dict(typed)

    assert "users" in legacy["tables"]
    assert legacy["tables"]["users"]["columns"][0]["type"] == "integer"
    
    orders_fks = legacy["tables"]["orders"].get("foreign_keys", [])
    assert len(orders_fks) > 0
    assert orders_fks[0]["referenced_table"] == "users"

def test_legacy_roundtrip_does_not_drop_core_schema_information_oracle():
    raw_schema_fixture = load_fixture("oracle_basic_schema.json")
    
    typed = from_legacy_schema(raw_schema_fixture, dialect="oracle")
    legacy = to_legacy_dict(typed)

    assert "USERS" in legacy["tables"]
    assert legacy["tables"]["USERS"]["columns"][0]["type"] == "NUMBER(10,0)"
    
    edges = legacy.get("graph", {}).get("edges", [])
    assert len(edges) > 0
    assert edges[0]["source"] == "ORDERS"
