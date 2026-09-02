"""Sprint 29.1 — postgres-specific execution integration tests (EXPLAIN, timeout).

Skipped safely when no local Docker PostgreSQL is reachable; runs in CI and
locally via `docker compose up -d postgres`. The shared seeded execution
battery moved to `test_adapter_conformance_matrix.py` (Sprint 29.7).
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


def _request(sql, timeout=2.0, max_rows=1000, mode=SQLExecutionMode.READ_ONLY, analyze=False):
    cfg = SQLDatabaseExecutionConfig(
        dialect=SQLDatabaseDialect.POSTGRESQL,
        timeout_seconds=timeout, max_rows=max_rows,
        execution_mode=mode, explain_analyze=analyze,
    )
    return SQLDatabaseExecutionRequest(
        case_id="c1", sql=sql, dialect=SQLDatabaseDialect.POSTGRESQL,
        fixture_ref=None, connection_ref="local_docker", config=cfg,
    )


def test_timeout_yields_execution_error(adapter):
    out = adapter.execute(_request("SELECT pg_sleep(2)", timeout=0.05))
    assert out.execution_error is not None
    assert out.rows == ()


_JOIN_SQL = (
    "SELECT c.name, o.id AS order_id "
    "FROM customers c JOIN orders o ON o.customer_id = c.id "
    "ORDER BY o.id"
)


def test_explain_only_returns_query_plan_rows(adapter):
    out = adapter.execute(_request(_JOIN_SQL, mode=SQLExecutionMode.EXPLAIN_ONLY))
    assert out.execution_error is None
    assert out.row_count >= 1
    # Postgres EXPLAIN result set has a single "QUERY PLAN" column.
    assert set(out.rows[0].keys()) == {"QUERY PLAN"}
    plan_text = "\n".join(str(r["QUERY PLAN"]) for r in out.rows)
    assert "Join" in plan_text or "Nested Loop" in plan_text or "Hash" in plan_text


def test_explain_only_does_not_leak_underlying_data(adapter):
    # A plain SELECT on customers, but in EXPLAIN mode we get plan lines,
    # never the customer rows themselves.
    out = adapter.execute(
        _request("SELECT id, name FROM customers ORDER BY id", mode=SQLExecutionMode.EXPLAIN_ONLY)
    )
    assert out.execution_error is None
    assert set(out.rows[0].keys()) == {"QUERY PLAN"}
    # The data column names must NOT appear as result keys.
    assert all(set(r.keys()) == {"QUERY PLAN"} for r in out.rows)


def test_explain_analyze_returns_actual_execution_plan(adapter):
    out = adapter.execute(
        _request(_JOIN_SQL, mode=SQLExecutionMode.EXPLAIN_ONLY, analyze=True)
    )
    assert out.execution_error is None
    plan_text = "\n".join(str(r["QUERY PLAN"]) for r in out.rows)
    # ANALYZE adds real execution measurements; assert structure, not timing.
    assert "actual time" in plan_text or "actual rows" in plan_text


def test_explain_only_max_rows_truncation(adapter):
    out = adapter.execute(
        _request(_JOIN_SQL, mode=SQLExecutionMode.EXPLAIN_ONLY, max_rows=1)
    )
    assert out.truncated is True
    assert out.row_count == 1
    assert any("truncat" in w.lower() for w in out.warnings)
