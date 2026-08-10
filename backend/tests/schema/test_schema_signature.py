from app.schema.schema_signature import (
    SCHEMA_SIGNATURE_VERSION,
    normalize_structure,
    compute_schema_signature,
)


def _schema(cols_order=("id", "email"), fk=True):
    users = {
        "columns": [
            {"name": cols_order[0], "type": "INTEGER", "primary_key": True, "nullable": False},
            {"name": cols_order[1], "type": "TEXT", "primary_key": False, "nullable": True},
        ],
        "foreign_keys": [],
    }
    orders = {
        "columns": [{"name": "id", "type": "INTEGER", "primary_key": True, "nullable": False},
                    {"name": "user_id", "type": "INTEGER", "primary_key": False, "nullable": True}],
        "foreign_keys": ([{"column": "user_id", "referenced_table": "users",
                           "referenced_column": "id"}] if fk else []),
    }
    return {"tables": {"users": users, "orders": orders}, "graph": {"nodes": [], "edges": []}}


def test_signature_is_deterministic():
    s = _schema()
    assert compute_schema_signature(normalize_structure(s)) == \
           compute_schema_signature(normalize_structure(s))


def test_signature_is_order_independent():
    # column order and table insertion order must not change the signature
    a = _schema(cols_order=("id", "email"))
    b = {"tables": {"orders": a["tables"]["orders"],
                    "users": {"columns": list(reversed(a["tables"]["users"]["columns"])),
                              "foreign_keys": []}},
         "graph": {"nodes": [], "edges": []}}
    assert compute_schema_signature(normalize_structure(a)) == \
           compute_schema_signature(normalize_structure(b))


def test_signature_changes_on_column_type_change():
    a = _schema()
    b = _schema()
    b["tables"]["users"]["columns"][1]["type"] = "VARCHAR(50)"
    assert compute_schema_signature(normalize_structure(a)) != \
           compute_schema_signature(normalize_structure(b))


def test_signature_changes_on_fk_removal():
    a = _schema(fk=True)
    b = _schema(fk=False)
    assert compute_schema_signature(normalize_structure(a)) != \
           compute_schema_signature(normalize_structure(b))


def test_signature_changes_with_version():
    n = normalize_structure(_schema())
    assert compute_schema_signature(n, version="v1") != compute_schema_signature(n, version="v2")


def test_empty_schema_is_stable():
    empty = {"tables": {}, "graph": {"nodes": [], "edges": []}}
    assert compute_schema_signature(normalize_structure(empty)) == \
           compute_schema_signature(normalize_structure({"tables": {}}))


def test_version_constant_is_v1():
    assert SCHEMA_SIGNATURE_VERSION == "v1"
