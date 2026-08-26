"""Sprint 29.3 — Oracle read-only execution integration tests (bare-Oracle, no seed).

Skipped safely when no local Docker Oracle is reachable. Real Oracle Docker
image + CI wiring land in Sprint 29.4; until then this whole module safe-skips.
Uses only bare-Oracle queries (DUAL / CONNECT BY LEVEL) — no seed schema.
"""
import pytest

from app.evaluation.oracle_connection_resolver import resolve_local_docker_connection
from app.evaluation.multi_database_execution import (
    SQLDatabaseDialect, SQLExecutionMode,
    SQLDatabaseExecutionConfig, SQLDatabaseExecutionRequest,
)
from app.evaluation.oracle_execution_adapter import OracleDatabaseExecutionAdapter

pytestmark = [pytest.mark.integration, pytest.mark.oracle]


def _local_docker_oracle_available():
    try:
        import oracledb
    except ImportError:
        return False
    conn = resolve_local_docker_connection()
    if conn is None:
        return False
    try:
        db = oracledb.connect(
            user=conn.user, password=conn.password,
            dsn=f"{conn.host}:{conn.port}/{conn.service_name}",
        )
        db.close()
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def adapter():
    if not _local_docker_oracle_available():
        pytest.skip("local Docker Oracle not available")
    return OracleDatabaseExecutionAdapter()


def _request(sql, timeout=2.0, max_rows=1000):
    cfg = SQLDatabaseExecutionConfig(
        dialect=SQLDatabaseDialect.ORACLE, timeout_seconds=timeout,
        max_rows=max_rows, execution_mode=SQLExecutionMode.READ_ONLY,
    )
    return SQLDatabaseExecutionRequest(
        case_id="c1", sql=sql, dialect=SQLDatabaseDialect.ORACLE,
        fixture_ref=None, connection_ref="local_docker", config=cfg,
    )


def test_select_from_dual_returns_named_dict_row(adapter):
    res = adapter.execute(_request("SELECT 1 AS n FROM DUAL"))
    assert res.execution_error is None
    assert res.row_count == 1
    assert list(res.rows[0].keys()) == ["N"]


def test_multi_column_select(adapter):
    res = adapter.execute(_request("SELECT 1 AS a, 'x' AS b FROM DUAL"))
    assert res.execution_error is None
    assert set(res.rows[0].keys()) == {"A", "B"}


def test_connect_by_level_truncates_to_max_rows(adapter):
    res = adapter.execute(
        _request("SELECT LEVEL AS lvl FROM DUAL CONNECT BY LEVEL <= 5", max_rows=2)
    )
    assert res.execution_error is None
    assert res.row_count == 2
    assert res.truncated is True


def test_slow_query_times_out(adapter):
    # A deliberately heavy row generator; call_timeout should cut it off.
    res = adapter.execute(
        _request("SELECT COUNT(*) AS c FROM DUAL CONNECT BY LEVEL <= 100000000", timeout=0.05)
    )
    assert res.execution_error is not None
