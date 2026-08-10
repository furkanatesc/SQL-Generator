from app.schema.schema_signature import normalize_structure, diff_structures


def _norm(tables):
    return normalize_structure({"tables": tables, "graph": {"nodes": [], "edges": []}})


def _users(type_email="TEXT"):
    return {"users": {"columns": [
        {"name": "id", "type": "INTEGER", "primary_key": True, "nullable": False},
        {"name": "email", "type": type_email, "primary_key": False, "nullable": True},
    ], "foreign_keys": []}}


def test_no_drift():
    d = diff_structures(_norm(_users()), _norm(_users()))
    assert d.has_drift is False
    assert d.as_dict()["added_tables"] == []


def test_added_and_removed_table():
    old = _norm(_users())
    new = _norm({**_users(), "orders": {"columns": [
        {"name": "id", "type": "INTEGER", "primary_key": True, "nullable": False}],
        "foreign_keys": []}})
    d = diff_structures(old, new)
    assert d.has_drift is True
    assert d.added_tables == ("orders",)
    assert d.removed_tables == ()
    # reverse direction removes it
    d2 = diff_structures(new, old)
    assert d2.removed_tables == ("orders",)


def test_added_and_removed_column():
    old = _norm(_users())
    new_tables = _users()
    new_tables["users"]["columns"].append(
        {"name": "age", "type": "INTEGER", "primary_key": False, "nullable": True})
    d = diff_structures(old, _norm(new_tables))
    assert ("users", "age") in d.added_columns
    assert d.has_drift is True


def test_changed_column_type():
    d = diff_structures(_norm(_users("TEXT")), _norm(_users("VARCHAR(50)")))
    assert d.changed_columns == (("users", "email", "TEXT", "VARCHAR(50)"),)
    assert d.has_drift is True


def test_added_and_removed_fk():
    with_fk = {"orders": {"columns": [
        {"name": "user_id", "type": "INTEGER", "primary_key": False, "nullable": True}],
        "foreign_keys": [{"column": "user_id", "referenced_table": "users",
                          "referenced_column": "id"}]}}
    without_fk = {"orders": {"columns": with_fk["orders"]["columns"], "foreign_keys": []}}
    d = diff_structures(_norm(without_fk), _norm(with_fk))
    assert d.added_fks == (("orders", "user_id", "users", "id"),)
    assert d.has_drift is True
