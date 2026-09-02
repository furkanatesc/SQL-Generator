# backend/tests/evaluation/test_adapter_conformance_matrix.py
"""Sprint 29.7 — cross-dialect adapter conformance matrix (live, seeded).

Single source of truth for the seeded read-only execution battery across the
four connection dialects. Safe-skips per dialect when its local Docker DB is not
reachable. Per-param markers preserve the existing `pytest -m <dialect>` CI
slicing: `backend-tests` runs all params (postgres live, others skip); each
`*-integration` job runs only its marked param live.
"""
import pytest

from app.evaluation.adapter_conformance import (
    profiles_for,
    fold,
    CaseFold,
)
from app.evaluation.multi_database_execution import (
    SQLDatabaseExecutionConfig,
    SQLDatabaseExecutionRequest,
    SQLExecutionMode,
)

_CONN_PROFILES = profiles_for(connection_based=True)


def _probe(profile):
    """Open+close a short-timeout connection with the dialect's driver.

    Driver-specific connect logic lives ONLY here (test-side), keeping the app
    module import-safe. Returns True iff a live local-Docker DB is reachable.
    """
    conn = profile.resolver()
    if conn is None:
        return False
    d = profile.dialect.value
    try:
        if d == "postgresql":
            import psycopg2
            db = psycopg2.connect(
                host=conn.host, port=conn.port, dbname=conn.dbname,
                user=conn.user, password=conn.password, connect_timeout=2,
            )
        elif d == "oracle":
            import oracledb
            db = oracledb.connect(
                user=conn.user, password=conn.password,
                dsn=f"{conn.host}:{conn.port}/{conn.service_name}", tcp_connect_timeout=2,
            )
        elif d == "mysql":
            import pymysql
            db = pymysql.connect(
                host=conn.host, port=conn.port, user=conn.user, password=conn.password,
                database=conn.database, connect_timeout=2,
            )
        elif d == "sqlserver":
            import pymssql
            db = pymssql.connect(
                server=conn.host, port=conn.port, user=conn.user, password=conn.password,
                database=conn.database, login_timeout=2,
            )
        else:  # pragma: no cover - registry only has the four above
            return False
        db.close()
        return True
    except Exception:
        return False


def _marks(profile):
    return [pytest.mark.integration, getattr(pytest.mark, profile.pytest_marker)]


_PARAMS = [pytest.param(p, marks=_marks(p), id=p.dialect.value) for p in _CONN_PROFILES]


def _adapter_or_skip(profile):
    if not _probe(profile):
        pytest.skip(f"local Docker {profile.dialect.value} not available")
    return profile.adapter_factory()


def _request(profile, sql, *, timeout=5.0, max_rows=1000):
    cfg = SQLDatabaseExecutionConfig(
        dialect=profile.dialect, timeout_seconds=timeout, max_rows=max_rows,
        execution_mode=SQLExecutionMode.READ_ONLY,
    )
    return SQLDatabaseExecutionRequest(
        case_id="c1", sql=sql, dialect=profile.dialect,
        fixture_ref=None, connection_ref="local_docker", config=cfg,
    )


@pytest.mark.parametrize("profile", _PARAMS)
def test_three_table_join_returns_named_rows(profile):
    adapter = _adapter_or_skip(profile)
    f = lambda k: fold(k, profile.case_fold)
    sql = (
        "SELECT c.name AS customer, o.status AS status, i.product_name AS product "
        "FROM customers c "
        "JOIN orders o ON o.customer_id = c.id "
        "JOIN order_items i ON i.order_id = o.id "
        "WHERE c.id = 1 AND o.id = 1 "
        "ORDER BY i.id"
    )
    res = adapter.execute(_request(profile, sql))
    assert res.execution_error is None
    assert set(res.rows[0].keys()) == {f("customer"), f("status"), f("product")}
    assert res.rows[0][f("customer")] == "Ada Lovelace"
    assert [r[f("product")] for r in res.rows] == ["Widget", "Gadget"]


@pytest.mark.parametrize("profile", _PARAMS)
def test_composite_fk_join(profile):
    adapter = _adapter_or_skip(profile)
    f = lambda k: fold(k, profile.case_fold)
    sql = (
        "SELECT v.label AS label, s.qty AS qty "
        "FROM product_variants v "
        "JOIN variant_stock s ON s.product_id = v.product_id AND s.sku = v.sku "
        "ORDER BY v.sku"
    )
    res = adapter.execute(_request(profile, sql))
    assert res.execution_error is None
    assert {r[f("label")] for r in res.rows} == {"Red Small", "Red Large"}
    assert {r[f("qty")] for r in res.rows} == {5, 3}


@pytest.mark.parametrize("profile", _PARAMS)
def test_max_rows_truncates(profile):
    adapter = _adapter_or_skip(profile)
    res = adapter.execute(_request(profile, "SELECT id FROM order_items ORDER BY id", max_rows=2))
    assert res.execution_error is None
    assert res.row_count == 2
    assert res.truncated is True
