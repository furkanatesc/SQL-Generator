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
    assert edges == [
        {
            "source": "orders",
            "target": "users",
            "source_col": "user_id",
            "target_col": "id",
            "type": "explicit"
        }
    ]
    
    # Original dict format matching
    assert legacy["tables"]["users"]["columns"][0]["primary_key"] is True

def test_legacy_roundtrip_does_not_drop_core_schema_information_postgres():
    raw_schema_fixture = load_fixture("postgres_basic_schema.json")
    
    typed = from_legacy_schema(raw_schema_fixture, dialect="postgres")
    legacy = to_legacy_dict(typed)

    assert "users" in legacy["tables"]
    assert legacy["tables"]["users"]["columns"][0]["type"] == "integer"
    
    orders_fks = legacy["tables"]["orders"].get("foreign_keys", [])
    assert orders_fks == [
        {
            "column": "user_id",
            "referenced_table": "users",
            "referenced_column": "id",
            "type": "explicit"
        }
    ]

def test_legacy_roundtrip_does_not_drop_core_schema_information_oracle():
    raw_schema_fixture = load_fixture("oracle_basic_schema.json")
    
    typed = from_legacy_schema(raw_schema_fixture, dialect="oracle")
    legacy = to_legacy_dict(typed)

    assert "USERS" in legacy["tables"]
    assert legacy["tables"]["USERS"]["columns"][0]["type"] == "NUMBER(10,0)"
    
    edges = legacy.get("graph", {}).get("edges", [])
    assert edges == [
        {
            "source": "ORDERS",
            "target": "USERS",
            "source_col": "USER_ID",
            "target_col": "ID",
            "type": "explicit"
        }
    ]

def test_from_legacy_schema_rejects_missing_tables():
    with pytest.raises(ValueError, match="Legacy schema must contain a 'tables' object"):
        from_legacy_schema({"graph": {}})

def test_from_legacy_schema_rejects_unknown_relationship_type():
    raw = {
        "tables": {
            "t1": {"columns": [{"name": "id"}]},
            "t2": {"columns": [{"name": "id"}]}
        },
        "graph": {
            "nodes": ["t1", "t2"],
            "edges": [
                {
                    "source": "t1",
                    "target": "t2",
                    "source_col": "id",
                    "target_col": "id",
                    "type": "unknown_magical_type"
                }
            ]
        }
    }
    with pytest.raises(ValueError, match=r"Unknown relationship type in graph edge\[0\]: unknown_magical_type"):
        from_legacy_schema(raw)

def test_from_legacy_schema_falls_back_to_foreign_keys_if_no_graph_edges():
    raw = {
        "tables": {
            "users": {
                "columns": [{"name": "id"}],
            },
            "orders": {
                "columns": [{"name": "id"}, {"name": "user_id"}],
                "foreign_keys": [
                    {
                        "column": "user_id",
                        "referenced_table": "users",
                        "referenced_column": "id",
                        "type": "explicit"
                    }
                ]
            }
        }
    }
    
    typed = from_legacy_schema(raw)
    assert typed.graph is not None
    assert set(typed.graph.nodes) == {"users", "orders"}
    assert len(typed.graph.edges) == 1
    assert typed.graph.edges[0].source_table == "orders"
    assert typed.graph.edges[0].target_table == "users"

def test_from_legacy_schema_rejects_malformed_table_and_column():
    # Table is not dict
    with pytest.raises(ValueError, match="Table 'users' metadata must be a dictionary"):
        from_legacy_schema({"tables": {"users": None}})
        
    # Column is not dict
    with pytest.raises(ValueError, match="Table 'users' column\\[0\\] must be a dictionary"):
        from_legacy_schema({"tables": {"users": {"columns": [None]}}})

def test_from_legacy_schema_rejects_malformed_graph_types():
    # nodes not list
    with pytest.raises(ValueError, match="Legacy schema 'graph.nodes' must be a list if present"):
        from_legacy_schema({
            "tables": {"users": {"columns": [{"name": "id"}]}}, 
            "graph": {"nodes": "users", "edges": []}
        })
        
    # edge not dict
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
    assert edges == [
        {
            "source": "orders",
            "target": "users",
            "source_col": "user_id",
            "target_col": "id",
            "type": "explicit"
        }
    ]
    
    # Original dict format matching
    assert legacy["tables"]["users"]["columns"][0]["primary_key"] is True

def test_legacy_roundtrip_does_not_drop_core_schema_information_postgres():
    raw_schema_fixture = load_fixture("postgres_basic_schema.json")
    
    typed = from_legacy_schema(raw_schema_fixture, dialect="postgres")
    legacy = to_legacy_dict(typed)

    assert "users" in legacy["tables"]
    assert legacy["tables"]["users"]["columns"][0]["type"] == "integer"
    
    orders_fks = legacy["tables"]["orders"].get("foreign_keys", [])
    assert orders_fks == [
        {
            "column": "user_id",
            "referenced_table": "users",
            "referenced_column": "id",
            "type": "explicit"
        }
    ]

def test_legacy_roundtrip_does_not_drop_core_schema_information_oracle():
    raw_schema_fixture = load_fixture("oracle_basic_schema.json")
    
    typed = from_legacy_schema(raw_schema_fixture, dialect="oracle")
    legacy = to_legacy_dict(typed)

    assert "USERS" in legacy["tables"]
    assert legacy["tables"]["USERS"]["columns"][0]["type"] == "NUMBER(10,0)"
    
    edges = legacy.get("graph", {}).get("edges", [])
    assert edges == [
        {
            "source": "ORDERS",
            "target": "USERS",
            "source_col": "USER_ID",
            "target_col": "ID",
            "type": "explicit"
        }
    ]

def test_from_legacy_schema_rejects_missing_tables():
    with pytest.raises(ValueError, match="Legacy schema must contain a 'tables' object"):
        from_legacy_schema({"graph": {}})

def test_from_legacy_schema_rejects_unknown_relationship_type():
    raw = {
        "tables": {
            "t1": {"columns": [{"name": "id"}]},
            "t2": {"columns": [{"name": "id"}]}
        },
        "graph": {
            "nodes": ["t1", "t2"],
            "edges": [
                {
                    "source": "t1",
                    "target": "t2",
                    "source_col": "id",
                    "target_col": "id",
                    "type": "unknown_magical_type"
                }
            ]
        }
    }
    with pytest.raises(ValueError, match=r"Unknown relationship type in graph edge\[0\]: unknown_magical_type"):
        from_legacy_schema(raw)

def test_from_legacy_schema_falls_back_to_foreign_keys_if_no_graph_edges():
    raw = {
        "tables": {
            "users": {
                "columns": [{"name": "id"}],
            },
            "orders": {
                "columns": [{"name": "id"}, {"name": "user_id"}],
                "foreign_keys": [
                    {
                        "column": "user_id",
                        "referenced_table": "users",
                        "referenced_column": "id",
                        "type": "explicit"
                    }
                ]
            }
        }
    }
    
    typed = from_legacy_schema(raw)
    assert typed.graph is not None
    assert set(typed.graph.nodes) == {"users", "orders"}
    assert len(typed.graph.edges) == 1
    assert typed.graph.edges[0].source_table == "orders"
    assert typed.graph.edges[0].target_table == "users"

def test_from_legacy_schema_rejects_malformed_table_and_column():
    # Table is not dict
    with pytest.raises(ValueError, match="Table 'users' metadata must be a dictionary"):
        from_legacy_schema({"tables": {"users": None}})
        
    # Column is not dict
    with pytest.raises(ValueError, match="Table 'users' column\\[0\\] must be a dictionary"):
        from_legacy_schema({"tables": {"users": {"columns": [None]}}})

def test_from_legacy_schema_rejects_malformed_graph_types():
    # nodes not list
    with pytest.raises(ValueError, match="Legacy schema 'graph.nodes' must be a list if present"):
        from_legacy_schema({
            "tables": {"users": {"columns": [{"name": "id"}]}}, 
            "graph": {"nodes": "users", "edges": []}
        })
        
    # edge not dict
    with pytest.raises(ValueError, match="Graph edge\\[0\\] must be a dictionary"):
        from_legacy_schema({
            "tables": {"users": {"columns": [{"name": "id"}]}}, 
            "graph": {"nodes": ["users"], "edges": [None]}
        })

def test_from_legacy_schema_fallback_on_empty_edges_list():
    raw = {
        "tables": {
            "orders": {
                "columns": [{"name": "id"}, {"name": "user_id"}],
                "foreign_keys": [
                    {"column": "user_id", "referenced_table": "users", "referenced_column": "id"}
                ]
            },
            "users": {"columns": [{"name": "id"}]}
        },
        "graph": {"nodes": ["orders", "users"], "edges": []}
    }
    
    typed = from_legacy_schema(raw)
    assert typed.graph is not None
    assert len(typed.relationships) == 1
    assert typed.relationships[0].source_table == "orders"
    assert typed.relationships[0].target_table == "users"

def test_from_legacy_schema_preserves_graph_edge_confidence_and_reason():
    raw_schema = {
        "tables": {
            "users": {"columns": [{"name": "id", "type": "int", "primary_key": True}]},
            "orders": {"columns": [{"name": "user_id", "type": "int"}]}
        },
        "graph": {
            "nodes": ["users", "orders"],
            "edges": [
                {
                    "source": "orders",
                    "source_col": "user_id",
                    "target": "users",
                    "target_col": "id",
                    "type": "implicit",
                    "confidence": 0.95,
                    "reason": "exact_match"
                }
            ]
        }
    }
    schema = from_legacy_schema(raw_schema)
    assert len(schema.relationships) == 1
    rel = schema.relationships[0]
    assert rel.relationship_type.value == "implicit"
    assert rel.confidence == 0.95
    assert rel.reason == "exact_match"