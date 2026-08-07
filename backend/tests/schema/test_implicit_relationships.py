import pytest
import json
import os
from app.schema.implicit_relationships import detect_implicit_relationships, resolve_target_key
from app.schema.schema_adapter import from_legacy_schema
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
    # v2: Rule 3 now requires the target column to BE the target table's resolved key.
    # Neither 'shipping' nor 'orders' declares a primary key and neither has an 'id'
    # column or a '<table>_id' convention column, so tracking_number is not a key in
    # either table -> the exact match is no longer treated as a spurious FK.
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

    assert semantic_edges(relationships) == set()


def test_rule1_targets_non_id_primary_key_recall():
    # users' PK is 'user_id' (not 'id'); orders.user_id must link to users.user_id
    schema = {"tables": {
        "users": {"columns": [{"name": "user_id", "primary_key": True}, {"name": "name"}]},
        "orders": {"columns": [{"name": "id", "primary_key": True}, {"name": "user_id"}]},
    }}
    rels = detect_implicit_relationships(schema)
    assert semantic_edges(rels) == {
        ("orders", "user_id", "users", "user_id", RelationshipType.IMPLICIT)}
    assert rels[0].reason == "singular_table_id_pattern"


def test_rule3_requires_target_key_drops_spurious_match():
    # both tables have 'tracking_number' but it is NOT a key in either -> no edge (precision)
    schema = {"tables": {
        "shipping": {"columns": [{"name": "id", "primary_key": True},
                                 {"name": "tracking_number"}]},
        "orders": {"columns": [{"name": "id", "primary_key": True},
                               {"name": "tracking_number"}]},
    }}
    rels = detect_implicit_relationships(schema)
    assert semantic_edges(rels) == set()


def test_rule3_matches_when_target_column_is_the_key():
    # orders.customer_id references customers whose PK IS 'customer_id' (natural key)
    schema = {"tables": {
        "customers": {"columns": [{"name": "customer_id", "primary_key": True},
                                  {"name": "name"}]},
        "orders": {"columns": [{"name": "id", "primary_key": True},
                               {"name": "customer_id"}]},
    }}
    rels = detect_implicit_relationships(schema)
    # 'customer_id' matches customers' PK 'customer_id' -> Rule 3 edge (0.60)
    edges = semantic_edges(rels)
    assert ("orders", "customer_id", "customers", "customer_id", RelationshipType.IMPLICIT) in edges


def test_rule3_positive_path_natural_key():
    # 'sku' is products' PK (natural key). inventory.sku matches it -> Rule 3 (NOT Rule 1,
    # since 'sku' has no _id suffix so Rule 1/2 never fire). Genuinely pins Rule 3's positive path.
    schema = {"tables": {
        "products": {"columns": [{"name": "sku", "primary_key": True}, {"name": "name"}]},
        "inventory": {"columns": [{"name": "id", "primary_key": True}, {"name": "sku"}]},
    }}
    rels = detect_implicit_relationships(schema)
    assert ("inventory", "sku", "products", "sku", RelationshipType.IMPLICIT) in semantic_edges(rels)
    r = next(x for x in rels if x.source_table == "inventory" and x.source_column == "sku")
    assert r.reason == "exact_non_generic_column_match"
    assert r.confidence == 0.60
    assert r.raw["rule"] == "exact_column_match"


def test_composite_pk_target_is_skipped():
    schema = {"tables": {
        "membership": {"columns": [{"name": "user_id", "primary_key": True},
                                   {"name": "group_id", "primary_key": True}]},
        "events": {"columns": [{"name": "id", "primary_key": True},
                               {"name": "membership_id"}]},
    }}
    rels = detect_implicit_relationships(schema)
    # membership has a composite PK -> resolve_target_key None -> no edge into membership
    assert all(r.target_table != "membership" for r in rels)

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

def _table(legacy_one):
    schema = from_legacy_schema({"tables": legacy_one}, "unknown")
    return schema.tables[0]

def test_resolve_target_key_declared_single_pk():
    t = _table({"users": {"columns": [
        {"name": "user_id", "primary_key": True}, {"name": "name"}]}})
    assert resolve_target_key(t) == "user_id"

def test_resolve_target_key_composite_pk_returns_none():
    t = _table({"membership": {"columns": [
        {"name": "user_id", "primary_key": True},
        {"name": "group_id", "primary_key": True}]}})
    assert resolve_target_key(t) is None

def test_resolve_target_key_convention_id_when_no_declared_pk():
    t = _table({"orders": {"columns": [{"name": "id"}, {"name": "total"}]}})
    assert resolve_target_key(t) == "id"

def test_resolve_target_key_convention_table_id_fallback():
    t = _table({"users": {"columns": [{"name": "user_id"}, {"name": "name"}]}})
    assert resolve_target_key(t) == "user_id"  # singular('users')+'_id'

def test_resolve_target_key_none_when_unresolvable():
    t = _table({"log": {"columns": [{"name": "message"}, {"name": "ts"}]}})
    assert resolve_target_key(t) is None

def test_resolve_target_key_declared_pk_wins_over_id_column():
    t = _table({"acct": {"columns": [
        {"name": "code", "primary_key": True}, {"name": "id"}]}})
    assert resolve_target_key(t) == "code"
