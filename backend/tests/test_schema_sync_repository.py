import pytest
from app.database import init_db, get_db_connection
from app import schema_sync_repository as repo


@pytest.fixture(autouse=True)
def _db():
    init_db()
    with get_db_connection() as conn:
        conn.execute("DELETE FROM schema_syncs")
        conn.commit()
    yield
    with get_db_connection() as conn:
        conn.execute("DELETE FROM schema_syncs")
        conn.commit()


def _schema(*cols):
    return {"tables": {"users": {"columns": [{"name": c, "type": "int"} for c in cols],
                                 "foreign_keys": []}}}


def test_first_sync_is_drifted_no_previous():
    s = repo.create_schema_sync("conn1", _schema("id"))
    assert s["previous_signature"] is None
    assert s["drifted"] == 1
    assert s["signature"]


def test_identical_second_sync_not_drifted():
    repo.create_schema_sync("conn1", _schema("id"))
    s2 = repo.create_schema_sync("conn1", _schema("id"))
    assert s2["drifted"] == 0
    assert s2["previous_signature"] is not None


def test_changed_second_sync_reports_drift():
    repo.create_schema_sync("conn1", _schema("id"))
    s2 = repo.create_schema_sync("conn1", _schema("id", "email"))
    assert s2["drifted"] == 1
    resp = repo.row_to_response_dict(s2)
    assert {"table": "users", "column": "email"} in resp["drift"]["added_columns"]


def test_per_connection_isolation():
    repo.create_schema_sync("conn1", _schema("id"))
    other = repo.create_schema_sync("conn2", _schema("id", "x"))
    assert other["previous_signature"] is None and other["drifted"] == 1


def test_list_filter_and_paginate():
    for _ in range(3):
        repo.create_schema_sync("conn1", _schema("id"))
    repo.create_schema_sync("conn2", _schema("id"))
    assert len(repo.list_schema_syncs(50, 0)) == 4
    assert len(repo.list_schema_syncs(50, 0, connection_id="conn1")) == 3
    assert len(repo.list_schema_syncs(2, 0, connection_id="conn1")) == 2


def test_get_and_delete():
    s = repo.create_schema_sync("conn1", _schema("id"))
    assert repo.get_schema_sync(s["id"])["id"] == s["id"]
    assert repo.delete_schema_sync(s["id"]) is True
    assert repo.get_schema_sync(s["id"]) is None
    assert repo.delete_schema_sync(s["id"]) is False


def test_malformed_schema_raises():
    with pytest.raises(ValueError):
        repo.create_schema_sync("conn1", {"not_tables": {}})
    with pytest.raises(ValueError):
        repo.create_schema_sync("conn1", "nope")


def test_response_dict_parses_json_fields():
    s = repo.create_schema_sync("conn1", _schema("id"))
    resp = repo.row_to_response_dict(repo.get_schema_sync(s["id"]))
    assert resp["drifted"] is True
    assert isinstance(resp["drift"], dict) and isinstance(resp["structure"], dict)
    assert "users" in resp["structure"]["tables"]
