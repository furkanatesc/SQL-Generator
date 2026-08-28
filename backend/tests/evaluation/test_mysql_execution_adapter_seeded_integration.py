"""Sprint 29.5 — MySQL seeded read-only execution integration tests.

Safe-skips when no local Docker MySQL is reachable. Requires the 29.5 seed
schema (tasks/fixtures/mysql/seed.sql) to have been applied. MySQL preserves
lowercase unquoted identifiers, so column keys assert lowercase names.
"""
import pytest

from app.evaluation.mysql_connection_resolver import resolve_local_docker_connection
from app.evaluation.multi_database_execution import (
    SQLDatabaseDialect, SQLExecutionMode,
    SQLDatabaseExecutionConfig, SQLDatabaseExecutionRequest,
)
from app.evaluation.mysql_execution_adapter import MySQLDatabaseExecutionAdapter

pytestmark = [pytest.mark.integration, pytest.mark.mysql]


def _local_docker_mysql_available():
    try:
        import pymysql
    except ImportError:
        return False
    conn = resolve_local_docker_connection()
    if conn is None:
        return False
    try:
        db = pymysql.connect(
            host=conn.host, port=conn.port, user=conn.user, password=conn.password,
            database=conn.database, connect_timeout=2,
        )
        db.close()
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def adapter():
    if not _local_docker_mysql_available():
        pytest.skip("local Docker MySQL not available")
    return MySQLDatabaseExecutionAdapter()


def _request(sql, timeout=5.0, max_rows=1000):
    cfg = SQLDatabaseExecutionConfig(
        dialect=SQLDatabaseDialect.MYSQL, timeout_seconds=timeout,
        max_rows=max_rows, execution_mode=SQLExecutionMode.READ_ONLY,
    )
    return SQLDatabaseExecutionRequest(
        case_id="c1", sql=sql, dialect=SQLDatabaseDialect.MYSQL,
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
    assert set(res.rows[0].keys()) == {"customer", "status", "product"}
    assert res.rows[0]["customer"] == "Ada Lovelace"
    assert [r["product"] for r in res.rows] == ["Widget", "Gadget"]


def test_composite_fk_join(adapter):
    sql = (
        "SELECT v.label AS label, s.qty AS qty "
        "FROM product_variants v "
        "JOIN variant_stock s ON s.product_id = v.product_id AND s.sku = v.sku "
        "ORDER BY v.sku"
    )
    res = adapter.execute(_request(sql))
    assert res.execution_error is None
    assert {r["label"] for r in res.rows} == {"Red Small", "Red Large"}
    assert {r["qty"] for r in res.rows} == {5, 3}


def test_max_rows_truncates_seeded_rows(adapter):
    res = adapter.execute(_request("SELECT id FROM order_items ORDER BY id", max_rows=2))
    assert res.execution_error is None
    assert res.row_count == 2
    assert res.truncated is True
