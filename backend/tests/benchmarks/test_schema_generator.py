from benchmarks.schema_generator import (
    generate_schema,
    generate_join_path_pairs,
    generate_selection_questions,
)
from app.schema.schema_adapter import from_legacy_schema
from app.schema.implicit_relationships import detect_implicit_relationships
from app.schema.schema_contract import RelationshipType


def test_generate_schema_is_deterministic():
    a = generate_schema(table_count=40, seed=7)
    b = generate_schema(table_count=40, seed=7)
    assert a == b


def test_generate_schema_produces_valid_database_schema():
    legacy = generate_schema(table_count=40, seed=7)
    schema = from_legacy_schema(legacy, "postgres")  # must not raise
    assert len(schema.tables) == 40
    assert len(schema.relationships) > 0  # explicit FKs to hubs


def test_generated_schema_yields_implicit_rule1_matches():
    legacy = generate_schema(table_count=60, seed=7)
    schema = from_legacy_schema(legacy, "postgres")
    rels = detect_implicit_relationships(schema)
    rule1 = [r for r in rels
             if r.raw.get("rule") == "singular_table_id_pattern"]
    assert len(rule1) > 0
    assert all(r.relationship_type == RelationshipType.IMPLICIT for r in rule1)


def test_different_seed_changes_schema():
    assert generate_schema(table_count=40, seed=1) != generate_schema(table_count=40, seed=2)


def test_table_names_unique_at_scale():
    legacy = generate_schema(table_count=200, seed=3)
    names = list(legacy["tables"].keys())
    assert len(names) == len(set(names)) == 200


def test_join_path_pairs_deterministic_and_distinct():
    names = [f"t{i}s" for i in range(50)]
    a = generate_join_path_pairs(names, seed=7, count=20)
    b = generate_join_path_pairs(names, seed=7, count=20)
    assert a == b
    assert all(src != tgt for src, tgt in a)
    assert all(src in names and tgt in names for src, tgt in a)


def test_selection_questions_deterministic_and_reference_tables():
    names = ["customers", "orders", "products"]
    a = generate_selection_questions(names, seed=7, count=10)
    b = generate_selection_questions(names, seed=7, count=10)
    assert a == b
    assert len(a) == 10
    # every question mentions at least one real table name
    assert all(any(n in q for n in names) for q in a)
