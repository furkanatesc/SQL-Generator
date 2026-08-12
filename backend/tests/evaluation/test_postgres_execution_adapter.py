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
from app.evaluation.postgres_execution_adapter import (
    normalize_postgres_execution_result,
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
