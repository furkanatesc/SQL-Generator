import uuid
import pytest
from app.database import init_db, get_db_connection
from app import admin_repository as repo

_TABLES = ("workspaces", "connections", "schema_syncs", "query_runs", "query_run_feedback")


@pytest.fixture(autouse=True)
def _db():
    init_db()
    with get_db_connection() as conn:
        for t in _TABLES:
            conn.execute(f"DELETE FROM {t}")
        conn.commit()
    yield
    with get_db_connection() as conn:
        for t in _TABLES:
            conn.execute(f"DELETE FROM {t}")
        conn.commit()


def test_counts_all_keys_zero_when_empty():
    c = repo.resource_counts()
    assert set(c.keys()) == set(_TABLES)
    assert all(v == 0 for v in c.values())


def test_counts_reflect_rows():
    with get_db_connection() as conn:
        conn.execute(
            "INSERT INTO workspaces (id, name, slug, description, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?)",
            (uuid.uuid4().hex, "W", "w", None, "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
        )
        conn.execute(
            "INSERT INTO query_runs (id, connection_id, sql, status, created_at) VALUES (?,?,?,?,?)",
            (uuid.uuid4().hex, "c1", "SELECT 1", "recorded", "2026-01-01T00:00:00"),
        )
        conn.execute(
            "INSERT INTO query_runs (id, connection_id, sql, status, created_at) VALUES (?,?,?,?,?)",
            (uuid.uuid4().hex, "c1", "SELECT 2", "recorded", "2026-01-01T00:00:00"),
        )
        conn.commit()
    c = repo.resource_counts()
    assert c["workspaces"] == 1 and c["query_runs"] == 2 and c["connections"] == 0
