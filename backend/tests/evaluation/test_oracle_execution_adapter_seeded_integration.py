"""Sprint 29.4 — Oracle seeded read-only execution integration tests.

Safe-skips when no local Docker Oracle is reachable. Requires the 29.4 seed
schema (tests/fixtures/oracle/seed.sql) to have been applied. Oracle folds
unquoted identifiers to UPPERCASE, so column keys assert uppercase names.
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
            tcp_connect_timeout=2,
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


def _request(sql, timeout=5.0, max_rows=1000):
    cfg = SQLDatabaseExecutionConfig(
        dialect=SQLDatabaseDialect.ORACLE, timeout_seconds=timeout,
        max_rows=max_rows, execution_mode=SQLExecutionMode.READ_ONLY,
    )
    return SQLDatabaseExecutionRequest(
        case_id="c1", sql=sql, dialect=SQLDatabaseDialect.ORACLE,
        fixture_ref=None, connection_ref="local_docker", config=cfg,
    )


def test_three_table_join_returns_named_rows(adapter):
    sql = (
        "SELECT c.name AS customer, o.status AS status, i.product_name AS product "
        "FROM customers c "
        "JOIN orders o ON o.customer_id = c.id "
        "JOIN order_items i ON i.order_id = o.id "
        "WHERE c.id = 1 AND o.id = 1 "
        "ORDER BY i.id"
    )
    res = adapter.execute(_request(sql))
    assert res.execution_error is None
    assert set(res.rows[0].keys()) == {"CUSTOMER", "STATUS", "PRODUCT"}
    assert res.rows[0]["CUSTOMER"] == "Ada Lovelace"
    assert [r["PRODUCT"] for r in res.rows] == ["Widget", "Gadget"]


def test_composite_fk_join(adapter):
    sql = (
        "SELECT v.label AS label, s.qty AS qty "
        "FROM product_variants v "
        "JOIN variant_stock s "
        "ON s.product_id = v.product_id AND s.sku = v.sku "
        "ORDER BY v.sku"
    )
    res = adapter.execute(_request(sql))
    assert res.execution_error is None
    assert {r["LABEL"] for r in res.rows} == {"Red Small", "Red Large"}
    assert {r["QTY"] for r in res.rows} == {5, 3}


def test_max_rows_truncates_seeded_rows(adapter):
    res = adapter.execute(_request("SELECT id FROM order_items ORDER BY id", max_rows=2))
    assert res.execution_error is None
    assert res.row_count == 2
    assert res.truncated is True
