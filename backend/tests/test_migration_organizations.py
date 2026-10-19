"""Sprint 33.0 Task 1 — migration v4 `organizations`."""
import sqlite3

import pytest

from app.migrations.app_db import APP_MIGRATIONS
from app.migrations.runner import migrate


def _conn(tmp_path):
    conn = sqlite3.connect(str(tmp_path / "app.db"))
    conn.row_factory = sqlite3.Row
    return conn


def _default_org(conn):
    rows = conn.execute("SELECT * FROM organizations WHERE slug = 'default'").fetchall()
    assert len(rows) == 1
    return rows[0]


def test_fresh_db_has_default_org_and_org_scoped_workspaces(tmp_path):
    conn = _conn(tmp_path)
    migrate(conn, APP_MIGRATIONS)
    assert conn.execute("SELECT COUNT(*) FROM organizations").fetchone()[0] == 1
    assert _default_org(conn)["name"] == "Default"
    cols = {r["name"]: r for r in conn.execute("PRAGMA table_info(workspaces)")}
    assert cols["organization_id"]["notnull"] == 1


def test_upgrade_moves_existing_workspaces_to_default_org(tmp_path):
    conn = _conn(tmp_path)
    migrate(conn, APP_MIGRATIONS[:3])
    for i in (1, 2):
        conn.execute(
            "INSERT INTO workspaces (id, name, slug, description, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (f"w{i}", f"N{i}", f"s{i}", f"d{i}", "t1", "t2"),
        )
    conn.commit()
    migrate(conn, APP_MIGRATIONS)
    org_id = _default_org(conn)["id"]
    rows = conn.execute("SELECT * FROM workspaces ORDER BY id").fetchall()
    assert len(rows) == 2
    for i, r in enumerate(rows, 1):
        assert (r["id"], r["name"], r["slug"], r["description"], r["created_at"], r["updated_at"]) == (
            f"w{i}", f"N{i}", f"s{i}", f"d{i}", "t1", "t2")
        assert r["organization_id"] == org_id


def test_workspace_slug_unique_per_org_only(tmp_path):
    conn = _conn(tmp_path)
    migrate(conn, APP_MIGRATIONS)
    sql = ("INSERT INTO workspaces (id, organization_id, name, slug, created_at, updated_at) "
           "VALUES (?, ?, 'n', 'same', 't', 't')")
    conn.execute(sql, ("a", "org1"))
    conn.execute(sql, ("b", "org2"))
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(sql, ("c", "org1"))


def test_migration_is_idempotent(tmp_path):
    conn = _conn(tmp_path)
    migrate(conn, APP_MIGRATIONS)
    status = migrate(conn, APP_MIGRATIONS)
    _default_org(conn)
    assert status.current == 4
    assert [r[0] for r in conn.execute("SELECT version FROM schema_migrations")][-1] == 4


def test_v4_function_rerun_on_migrated_db_is_noop(tmp_path):
    from app.migrations.app_db import _organizations
    conn = _conn(tmp_path)
    migrate(conn, APP_MIGRATIONS[:3])
    for i in (1, 2):
        conn.execute(
            "INSERT INTO workspaces (id, name, slug, description, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (f"w{i}", f"N{i}", f"s{i}", f"d{i}", "t1", "t2"),
        )
    conn.commit()
    migrate(conn, APP_MIGRATIONS)
    orgs_before = [tuple(r) for r in conn.execute("SELECT * FROM organizations ORDER BY id")]
    ws_before = [tuple(r) for r in conn.execute("SELECT * FROM workspaces ORDER BY id")]
    org_id = _default_org(conn)["id"]
    _organizations(conn)
    conn.commit()
    assert [tuple(r) for r in conn.execute("SELECT * FROM organizations ORDER BY id")] == orgs_before
    assert [tuple(r) for r in conn.execute("SELECT * FROM workspaces ORDER BY id")] == ws_before
    assert conn.execute("SELECT COUNT(*) FROM organizations").fetchone()[0] == 1
    assert _default_org(conn)["id"] == org_id
