"""Sprint 29.1 — read-only execution integration tests (seeded schema).

Skipped safely when no local Docker PostgreSQL is reachable; runs in CI and
locally via `docker compose up -d postgres`.
"""
import pytest

from app.evaluation.postgres_connection_resolver import resolve_local_docker_connection
from app.evaluation.multi_database_execution import (
    SQLDatabaseDialect,
    SQLExecutionMode,
    SQLDatabaseExecutionConfig,
    SQLDatabaseExecutionRequest,
)
from app.evaluation.postgres_execution_adapter import PostgresDatabaseExecutionAdapter

pytestmark = [pytest.mark.integration, pytest.mark.postgres]


def _local_docker_postgres_available():
    try:
        import psycopg2
    except ImportError:
        return False
    conn = resolve_local_docker_connection()
    if conn is None:
        return False
    try:
        db = psycopg2.connect(
            host=conn.host, port=conn.port, dbname=conn.dbname,
            user=conn.user, password=conn.password, connect_timeout=2,
        )
        db.close()
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def adapter():
    if not _local_docker_postgres_available():
        pytest.skip("local Docker PostgreSQL not available")
    return PostgresDatabaseExecutionAdapter()


def _request(sql, timeout=2.0, max_rows=1000):
    cfg = SQLDatabaseExecutionConfig(
        dialect=SQLDatabaseDialect.POSTGRESQL,
        timeout_seconds=timeout, max_rows=max_rows,
        execution_mode=SQLExecutionMode.READ_ONLY,
    )
    return SQLDatabaseExecutionRequest(
        case_id="c1", sql=sql, dialect=SQLDatabaseDialect.POSTGRESQL,
        fixture_ref=None, connection_ref="local_docker", config=cfg,
    )


def test_select_returns_named_dict_rows(adapter):
    out = adapter.execute(_request("SELECT id, name FROM customers ORDER BY id"))
    assert out.execution_error is None
    assert out.row_count >= 1
    first = out.rows[0]
    assert set(first.keys()) == {"id", "name"}


def test_multi_table_join(adapter):
    sql = (
        "SELECT c.name, o.id AS order_id "
        "FROM customers c JOIN orders o ON o.customer_id = c.id "
        "ORDER BY o.id"
    )
    out = adapter.execute(_request(sql))
    assert out.execution_error is None
    assert out.row_count >= 1
    assert set(out.rows[0].keys()) == {"name", "order_id"}


def test_max_rows_truncation(adapter):
    out = adapter.execute(_request("SELECT id FROM customers ORDER BY id", max_rows=1))
    assert out.truncated is True
    assert out.row_count == 1
    assert any("truncat" in w.lower() for w in out.warnings)


def test_timeout_yields_execution_error(adapter):
    out = adapter.execute(_request("SELECT pg_sleep(2)", timeout=0.05))
    assert out.execution_error is not None
    assert out.rows == ()
