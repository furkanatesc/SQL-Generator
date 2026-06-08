import pytest
import json
import os
from app.schema.implicit_relationships import detect_implicit_relationships
from app.schema.schema_contract import RelationshipType

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "..", "fixtures", "schema")

def load_fixture(filename: str) -> dict:
    with open(os.path.join(FIXTURES_DIR, filename), "r", encoding="utf-8") as f:
        return json.load(f)

def semantic_edges(relationships) -> set:
    return {
        (rel.source_table, rel.source_column, rel.target_table, rel.target_column, rel.relationship_type)
        for rel in relationships
    }

def test_implicit_relationship_detects_table_id_pattern():
    schema = load_fixture("implicit_relationship_positive_schema.json")
    relationships = detect_implicit_relationships(schema)

    assert semantic_edges(relationships) == {
        ("orders", "user_id", "users", "id", RelationshipType.IMPLICIT)
    }

    rel = relationships[0]
    assert rel.confidence >= 0.85
    assert rel.reason == "singular_table_id_pattern"
    assert rel.raw["rule"] == "singular_table_id_pattern"
    assert rel.raw["matched_prefix"] == "user"

def test_implicit_relationship_rejects_generic_status_column_match():
    schema = load_fixture("implicit_relationship_false_positive_schema.json")
    relationships = detect_implicit_relationships(schema)
    assert semantic_edges(relationships) == set()

def test_implicit_relationship_rejects_generic_name_column_match():
    schema = {
        "tables": {
            "products": {
                "columns": [{"name": "name"}]
            },
            "customers": {
                "columns": [{"name": "name"}]
            }
        }
    }
    relationships = detect_implicit_relationships(schema)
    assert semantic_edges(relationships) == set()

def test_fuzzy_relationship_requires_minimum_score():
    # In the fuzzy schema: employees.departmnt_manager_id -> prefix: departmnt_manager
    # departments singular: department
    # Let's adjust fuzzy schema to match prefix to table
    schema = {
        "tables": {
            "departments": {
                "columns": [{"name": "id", "type": "INTEGER"}]
            },
            "employees": {
                "columns": [{"name": "departmnt_id", "type": "INTEGER"}]
            }
        }
    }
    relationships = detect_implicit_relationships(schema)

    assert semantic_edges(relationships) == {
        ("employees", "departmnt_id", "departments", "id", RelationshipType.IMPLICIT_FUZZY)
    }
    rel = relationships[0]
    assert rel.confidence >= 0.65
    assert rel.reason == "fuzzy_prefix_to_table_match"
    assert "ratio" in rel.raw

def test_explicit_fk_relationships_are_not_modified_by_implicit_detection():
    schema = load_fixture("schema_with_explicit_fk.json")
    implicit = detect_implicit_relationships(schema)
    assert semantic_edges(implicit) == set()

def test_exact_non_generic_column_match_is_unidirectional():
    schema = {
        "tables": {
            "shipping": {
                "columns": [{"name": "tracking_number", "type": "VARCHAR"}]
            },
            "orders": {
                "columns": [{"name": "tracking_number", "type": "VARCHAR"}]
            }
        }
    }
    relationships = detect_implicit_relationships(schema)
    
    # It should generate EXACTLY ONE edge, not two. Order doesn't matter, just length 1.
    assert len(relationships) == 1
    rel = relationships[0]
    assert rel.relationship_type == RelationshipType.IMPLICIT
    assert rel.confidence == 0.60
    assert rel.reason == "exact_non_generic_column_match"

    assert semantic_edges(relationships) == {
        (rel.source_table, "tracking_number", rel.target_table, "tracking_number", RelationshipType.IMPLICIT)
    }

def test_get_singular_logic_with_complex_plural_endings():
    schema = {
        "tables": {
            "categories": {
                "columns": [{"name": "id", "type": "INTEGER"}]
            },
            "products": {
                "columns": [{"name": "category_id", "type": "INTEGER"}]
            },
            "companies": {
                "columns": [{"name": "id", "type": "INTEGER"}]
            },
            "users": {
                "columns": [{"name": "company_id", "type": "INTEGER"}]
            }
        }
    }
    relationships = detect_implicit_relationships(schema)
    
    assert semantic_edges(relationships) == {
        ("products", "category_id", "categories", "id", RelationshipType.IMPLICIT),
        ("users", "company_id", "companies", "id", RelationshipType.IMPLICIT)
    }
