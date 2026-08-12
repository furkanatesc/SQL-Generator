"""Sprint 25.8 — PostgreSQL read-only adapter integration tests.

These tests exercise the REAL execution path against a local Docker PostgreSQL.
They are skipped safely when no local Docker PostgreSQL is reachable (e.g. local
dev without Docker), and run in CI when a `postgres` service container is
provided. Connection params come from POSTGRES_TEST_* env vars (local defaults).
"""

import json

import pytest

from app.evaluation.postgres_adapter import (
    SQLPostgresAdapterConfig,
    SQLPostgresAdapterContract,
    SQLPostgresAdapterExecutionRequest,
    SQLPostgresAdapterStatus,
)

pytestmark = [pytest.mark.integration, pytest.mark.postgres]


def _make_test_connection():
    """Build a local-Docker connection via the shared 29.0 resolver."""
    from app.evaluation.postgres_connection_resolver import resolve_local_docker_connection
    return resolve_local_docker_connection()


def _local_docker_postgres_available():
    """Return True only if psycopg2 is installed AND a local Docker PostgreSQL
    is reachable. Never raises — this is the safe skip gate."""
    try:
        import psycopg2
    except ImportError:
        return False
    conn = _make_test_connection()
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


def _request(sql, *, case_id="it", timeout_seconds=2.0, max_rows=1000):
    return SQLPostgresAdapterExecutionRequest(
        case_id=case_id,
        sql=sql,
        dialect="postgresql",
        config=SQLPostgresAdapterConfig(timeout_seconds=timeout_seconds, max_rows=max_rows),
    )


@pytest.fixture(scope="module")
def pg_adapter():
    if not _local_docker_postgres_available():
        pytest.skip("local Docker PostgreSQL not available")
    return SQLPostgresAdapterContract(connection=_make_test_connection())


def test_skip_gate_is_safe_without_docker():
    """The availability gate must always return a bool and never raise,
    so that the absence of Docker yields a controlled skip (not a failure)."""
    result = _local_docker_postgres_available()
    assert isinstance(result, bool)


def test_postgres_adapter_executes_select_against_local_docker_postgres(pg_adapter):
    result = pg_adapter.execute(_request("SELECT 1 AS one, 'hello' AS greeting"))
    assert result.status == SQLPostgresAdapterStatus.EXECUTED
    assert result.row_count == 1
    assert result.rows == ((1, "hello"),)
    assert result.truncated is False
    assert result.duration_ms >= 0.0


def test_postgres_adapter_enforces_max_rows(pg_adapter):
    result = pg_adapter.execute(
        _request("SELECT * FROM generate_series(1, 100) AS s", max_rows=10)
    )
    assert result.status == SQLPostgresAdapterStatus.EXECUTED
    assert result.row_count == 10
    assert result.truncated is True
    assert any("truncated" in w for w in result.warnings)


def test_postgres_adapter_returns_deterministic_executed_result_shape(pg_adapter):
    result = pg_adapter.execute(_request("SELECT 42 AS answer"))
    serialized = result.to_dict()
    assert set(serialized.keys()) == {
        "version", "case_id", "status", "sql_sha256",
        "rows", "row_count", "truncated", "error", "warnings", "columns", "duration_ms",
    }
    assert serialized["status"] == "executed"
    assert serialized["rows"] == [[42]]
    assert serialized["columns"] == ["answer"]
    json.dumps(serialized)  # must be JSON-serializable


def test_postgres_adapter_executed_result_does_not_leak_credentials(pg_adapter):
    result = pg_adapter.execute(_request("SELECT 1"))
    serialized_str = json.dumps(result.to_dict())
    assert "sqlgen" not in serialized_str  # connection user/password must not leak
    assert "localhost" not in serialized_str


def test_postgres_adapter_timeout_is_enforced_or_reported_deterministically(pg_adapter):
    result = pg_adapter.execute(
        _request("SELECT pg_sleep(3)", timeout_seconds=1.0)
    )
    assert result.status == SQLPostgresAdapterStatus.EXECUTION_ERROR
    assert "timed out" in (result.error or "").lower()


def test_postgres_adapter_write_is_blocked_even_with_live_connection(pg_adapter):
    # Defense-in-depth: the validator rejects writes before the DB is touched.
    result = pg_adapter.execute(_request("DROP TABLE IF EXISTS anything"))
    assert result.status == SQLPostgresAdapterStatus.REJECTED
