import pytest
from app.database import init_db, get_db_connection
from app import connection_repository as repo
from app.evaluation.connection_abstraction import SQLConnectionAbstractionContractError


@pytest.fixture(autouse=True)
def _db():
    init_db()
    with get_db_connection() as conn:
        conn.execute("DELETE FROM connections")
        conn.commit()
    yield
    with get_db_connection() as conn:
        conn.execute("DELETE FROM connections")
        conn.commit()


def _mk(**over):
    base = dict(
        connection_ref="pg-local", workspace_id=None, name="PG Local",
        dialect="postgresql", environment="local", host="localhost",
        port=5432, database="sqlgen", auth_mode="secret_ref",
        secret_provider="env", secret_key="PG_PASSWORD",
        max_rows=1000, timeout_seconds=2.0,
    )
    base.update(over)
    return base


def test_create_and_get():
    c = repo.create_connection(**_mk())
    assert c["id"] and c["connection_ref"] == "pg-local"
    assert c["access_mode"] == "read_only"
    assert c["secret_provider"] == "env" and c["secret_key"] == "PG_PASSWORD"
    assert repo.get_connection(c["id"])["id"] == c["id"]
    assert repo.get_by_ref("pg-local")["id"] == c["id"]


def test_duplicate_ref_raises():
    repo.create_connection(**_mk())
    with pytest.raises(repo.ConnectionRefConflict):
        repo.create_connection(**_mk(name="Other"))


def test_auth_none_forbids_secret_ref():
    with pytest.raises(SQLConnectionAbstractionContractError):
        repo.create_connection(**_mk(auth_mode="none"))  # secret_ref still provided


def test_secret_ref_required_for_secret_ref_mode():
    with pytest.raises(SQLConnectionAbstractionContractError):
        repo.create_connection(**_mk(secret_provider=None, secret_key=None))


def test_raw_secret_in_key_rejected():
    with pytest.raises(SQLConnectionAbstractionContractError):
        repo.create_connection(**_mk(secret_key="postgres://user:pass@host/db"))


def test_bad_port_rejected():
    with pytest.raises(SQLConnectionAbstractionContractError):
        repo.create_connection(**_mk(port=99999))


def test_list_filter_by_workspace_and_paginate():
    repo.create_connection(**_mk(connection_ref="a", workspace_id="ws1"))
    repo.create_connection(**_mk(connection_ref="b", workspace_id="ws1"))
    repo.create_connection(**_mk(connection_ref="c", workspace_id="ws2"))
    assert len(repo.list_connections(limit=50, offset=0)) == 3
    assert len(repo.list_connections(limit=50, offset=0, workspace_id="ws1")) == 2
    assert len(repo.list_connections(limit=1, offset=0, workspace_id="ws1")) == 1


def test_update_whitelist_revalidates():
    c = repo.create_connection(**_mk())
    up = repo.update_connection(c["id"], name="Renamed", port=5433)
    assert up["name"] == "Renamed" and up["port"] == 5433
    with pytest.raises(SQLConnectionAbstractionContractError):
        repo.update_connection(c["id"], port=0)


def test_update_missing_returns_none():
    assert repo.update_connection("nope", name="x") is None


def test_update_auth_mode_to_none_clears_secret():
    # regression: transitioning secret_ref -> none must clear the stored secret,
    # otherwise the domain invariant makes the 'none' state unreachable (422 dead-end).
    c = repo.create_connection(**_mk())
    up = repo.update_connection(c["id"], auth_mode="none")
    assert up["auth_mode"] == "none"
    assert up["secret_provider"] is None and up["secret_key"] is None
    resp = repo.row_to_response_dict(up)
    assert resp["secret_ref"] is None


def test_delete():
    c = repo.create_connection(**_mk())
    assert repo.delete_connection(c["id"]) is True
    assert repo.get_connection(c["id"]) is None
    assert repo.delete_connection(c["id"]) is False


def test_row_to_response_dict_has_no_raw_secret_and_nested_endpoint():
    c = repo.create_connection(**_mk())
    resp = repo.row_to_response_dict(repo.get_connection(c["id"]))
    assert resp["endpoint"] == {"host": "localhost", "port": 5432, "database": "sqlgen"}
    assert resp["secret_ref"] == {"provider": "env", "key": "PG_PASSWORD"}
    assert "secret_provider" not in resp and "secret_key" not in resp
