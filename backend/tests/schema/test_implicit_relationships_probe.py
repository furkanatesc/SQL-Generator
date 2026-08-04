from app.schema.schema_adapter import from_legacy_schema
from app.schema.implicit_relationships import detect_implicit_relationships
from app.schema.profiling import ProfileProbe


def _schema():
    legacy = {
        "tables": {
            "customers": {"columns": [{"name": "id", "primary_key": True}], "foreign_keys": []},
            "orders": {"columns": [{"name": "id", "primary_key": True},
                                   {"name": "custommer_id"}], "foreign_keys": []},
        }
    }
    return from_legacy_schema(legacy, "postgres")


def test_probe_none_preserves_output():
    schema = _schema()
    before = detect_implicit_relationships(schema)
    after = detect_implicit_relationships(schema, probe=None)
    assert [r.model_dump() for r in before] == [r.model_dump() for r in after]


def test_probe_counts_pairs_and_fuzzy():
    schema = _schema()
    probe = ProfileProbe()
    detect_implicit_relationships(schema, probe=probe)
    # 2 tables -> 2 ordered pairs with src != tgt
    assert probe.counts.get("pair_iteration", 0) == 2
    # 'custommer_id' fuzzy-matches 'customer' -> at least one fuzzy comparison
    assert probe.counts.get("fuzzy_comparison", 0) >= 1
