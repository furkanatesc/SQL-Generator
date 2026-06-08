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
    # The fixture contains id, status, name on both sides. None of these should match.
    assert len(relationships) == 0

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
    assert len(relationships) == 0

def test_fuzzy_relationship_requires_minimum_score():
    schema = load_fixture("implicit_relationship_fuzzy_schema.json")
    relationships = detect_implicit_relationships(schema)

    assert len(relationships) > 0
    for rel in relationships:
        assert rel.relationship_type == RelationshipType.IMPLICIT_FUZZY
        assert rel.confidence >= 0.65
        assert rel.reason == "fuzzy_column_match"
        assert "ratio" in rel.raw

def test_implicit_relationships_require_confidence_and_reason():
    schema = load_fixture("implicit_relationship_fuzzy_schema.json")
    relationships = detect_implicit_relationships(schema)

    assert len(relationships) > 0
    for rel in relationships:
        assert rel.relationship_type in {
            RelationshipType.IMPLICIT,
            RelationshipType.IMPLICIT_FUZZY,
        }
        assert rel.confidence is not None
        assert 0.0 <= rel.confidence <= 1.0
        assert bool(rel.reason)

def test_explicit_fk_relationships_are_not_modified_by_implicit_detection():
    schema = load_fixture("schema_with_explicit_fk.json")
    implicit = detect_implicit_relationships(schema)

    # orders.user_id -> users.id is an exact singular_table_id_pattern match, 
    # but it's already defined as explicit in the fixture. 
    # The detection should skip it.
    assert len(implicit) == 0

def test_exact_non_generic_column_match():
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
    
    assert len(relationships) > 0
    rel = relationships[0]
    assert rel.relationship_type == RelationshipType.IMPLICIT
    assert rel.confidence == 0.60
    assert rel.reason == "exact_non_generic_column_match"
