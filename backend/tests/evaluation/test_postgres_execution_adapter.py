import hashlib
import pytest

from app.evaluation.multi_database_execution import (
    SQLDatabaseDialect,
    SQLExecutionMode,
    SQLDatabaseExecutionConfig,
    SQLDatabaseExecutionRequest,
    SQLDatabaseExecutionResult,
)
from app.evaluation.postgres_adapter import (
    SQLPostgresAdapterExecutionResult,
    SQLPostgresAdapterStatus,
    SQL_POSTGRES_ADAPTER_CONTRACT_VERSION,
)
from app.evaluation.multi_database_execution import (
    SQLExecutionAdapterCapability,
    SQLMultiDatabaseExecutionContractError,
    SQLDatabaseExecutionRouter,
)
from app.evaluation.postgres_execution_adapter import (
    normalize_postgres_execution_result,
    PostgresDatabaseExecutionAdapter,
)

SQL = "SELECT id, name FROM customers"


def _request(sql=SQL):
    cfg = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.POSTGRESQL)
    return SQLDatabaseExecutionRequest(
        case_id="c1", sql=sql, dialect=SQLDatabaseDialect.POSTGRESQL,
        fixture_ref=None, connection_ref="local_docker", config=cfg,
    )


def _pg(status, **kw):
    h = hashlib.sha256(SQL.encode()).hexdigest()
    return SQLPostgresAdapterExecutionResult(
        version=SQL_POSTGRES_ADAPTER_CONTRACT_VERSION, case_id="c1",
        status=status, sql_sha256=h, **kw,
    )


def test_normalize_executed_maps_rows_to_dicts():
    pg = _pg(SQLPostgresAdapterStatus.EXECUTED,
             rows=((1, "a"), (2, "b")), row_count=2,
             columns=("id", "name"), duration_ms=1.5)
    out = normalize_postgres_execution_result(pg, _request())
    assert isinstance(out, SQLDatabaseExecutionResult)
    assert out.dialect == SQLDatabaseDialect.POSTGRESQL
    assert out.rows == ({"id": 1, "name": "a"}, {"id": 2, "name": "b"})
    assert out.row_count == 2
    assert out.execution_error is None
    assert out.sql_sha256 == hashlib.sha256(SQL.encode()).hexdigest()


def test_normalize_executed_column_count_mismatch_falls_back_with_warning():
    pg = _pg(SQLPostgresAdapterStatus.EXECUTED,
             rows=((1, "a"),), row_count=1, columns=("id",))  # 1 col, 2 values
    out = normalize_postgres_execution_result(pg, _request())
    assert out.rows == ({"col_0": 1, "col_1": "a"},)
    assert any("column" in w.lower() for w in out.warnings)


@pytest.mark.parametrize("status", [
    SQLPostgresAdapterStatus.REJECTED,
    SQLPostgresAdapterStatus.EXECUTION_ERROR,
    SQLPostgresAdapterStatus.NOT_IMPLEMENTED,
])
def test_normalize_non_executed_sets_error_and_empty_rows(status):
    pg = _pg(status, error="boom")
    out = normalize_postgres_execution_result(pg, _request())
    assert out.rows == ()
    assert out.row_count == 0
    assert out.execution_error == "boom"


def test_normalize_carries_truncation_and_warnings():
    pg = _pg(SQLPostgresAdapterStatus.EXECUTED, rows=((1, "a"),), row_count=1,
             columns=("id", "name"), truncated=True,
             warnings=("result truncated to max_rows",))
    out = normalize_postgres_execution_result(pg, _request())
    assert out.truncated is True
    assert "result truncated to max_rows" in out.warnings


def _adapter(resolver):
    return PostgresDatabaseExecutionAdapter(connection_resolver=resolver)


def test_adapter_dialect_and_capabilities():
    a = _adapter(lambda env=None: None)
    assert a.dialect == SQLDatabaseDialect.POSTGRESQL
    assert a.capabilities() == (
        SQLExecutionAdapterCapability.CONNECTION_REF,
        SQLExecutionAdapterCapability.READ_ONLY,
    )


def test_adapter_requires_connection_ref_rejects_fixture():
    a = _adapter(lambda env=None: None)
    cfg = SQLDatabaseExecutionConfig(dialect=SQLDatabaseDialect.POSTGRESQL)
    req = SQLDatabaseExecutionRequest(
        case_id="c1", sql=SQL, dialect=SQLDatabaseDialect.POSTGRESQL,
        fixture_ref="somefix", connection_ref=None, config=cfg,
    )
    with pytest.raises(SQLMultiDatabaseExecutionContractError):
        a.execute(req)


def test_adapter_rejects_explain_only_mode():
    a = _adapter(lambda env=None: None)
    cfg = SQLDatabaseExecutionConfig(
        dialect=SQLDatabaseDialect.POSTGRESQL,
        execution_mode=SQLExecutionMode.EXPLAIN_ONLY,
    )
    req = SQLDatabaseExecutionRequest(
        case_id="c1", sql=SQL, dialect=SQLDatabaseDialect.POSTGRESQL,
        fixture_ref=None, connection_ref="local_docker", config=cfg,
    )
    with pytest.raises(SQLMultiDatabaseExecutionContractError):
        a.execute(req)


def test_adapter_no_connection_returns_graceful_error():
    a = _adapter(lambda env=None: None)  # resolver yields no connection
    out = a.execute(_request())
    assert out.rows == ()
    assert out.row_count == 0
    assert out.execution_error is not None
    assert out.dialect == SQLDatabaseDialect.POSTGRESQL


def test_adapter_pluggable_into_router():
    a = _adapter(lambda env=None: None)
    router = SQLDatabaseExecutionRouter(adapters=(a,))
    assert router.get_adapter(SQLDatabaseDialect.POSTGRESQL) is a


def test_execution_adapter_import_does_not_load_db_drivers():
    import os
    import subprocess
    import sys
    import app.evaluation
    eval_dir = os.path.dirname(app.evaluation.__file__)

    code = (
        "import sys\n"
        f"sys.path.insert(0, {repr(eval_dir)})\n"
        "import postgres_execution_adapter\n"
        "forbidden = ['psycopg', 'psycopg2', 'asyncpg', 'sqlalchemy']\n"
        "for mod in forbidden:\n"
        "    if mod in sys.modules:\n"
        "        print(f'FORBIDDEN:{mod}')\n"
    )
    res = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "FORBIDDEN" not in res.stdout, (
        f"Importing postgres_execution_adapter loaded forbidden driver: {res.stdout}"
    )
    # Note: the 25.8 network-client isolation test (forbidden = requests/urllib/
    # http.client/asyncio/socket) was investigated and deliberately NOT ported here.
    # Unlike postgres_adapter.py (25.8), this module's own top-level imports reach
    # into sibling app.evaluation.* modules, which forces Python to fully execute
    # app/evaluation/__init__.py's eager re-export chain -- including
    # postgres_schema_adapter -> app.schema.schema_contract -> pydantic. Pydantic
    # itself references asyncio/socket internally for its typing machinery (e.g.
    # AnyUrl/IPvAnyAddress validators), with no actual network I/O at import time.
    # Verified via bisection (see task-4-report.md) that no driver (psycopg/
    # psycopg2/asyncpg/sqlalchemy) nor any genuine network client (requests/httpx/
    # qdrant/etc.) is imported anywhere in the chain -- only pydantic's incidental
    # stdlib references. Porting the 25.8 network forbidden-list verbatim would
    # therefore be a false positive, not a real isolation leak.
