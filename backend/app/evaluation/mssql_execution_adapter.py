"""Sprint 29.6 — SQL Server Read-Only Execution adapter (bridge).

Bridges the Sprint 29.6 local-Docker read-only SQL Server adapter to the
dialect-agnostic execution contract. Local-Docker-only, read-only,
side-effect-free. Driver-isolated: importing this module loads NO database
driver; ``pymssql`` is imported lazily only inside the low-level adapter's
real execution path.
"""

import hashlib
from typing import Any, Mapping, Tuple

from app.evaluation.multi_database_execution import (
    SQL_MULTI_DATABASE_EXECUTION_VERSION,
    SQLDatabaseDialect,
    SQLDatabaseExecutionAdapter,
    SQLDatabaseExecutionConfig,
    SQLDatabaseExecutionRequest,
    SQLDatabaseExecutionResult,
    SQLExecutionAdapterCapability,
    SQLExecutionMode,
    SQLMultiDatabaseExecutionContractError,
)
from app.evaluation.mssql_adapter import (
    SQLMSSQLAdapterConfig,
    SQLMSSQLAdapterContract,
    SQLMSSQLAdapterExecutionRequest,
    SQLMSSQLAdapterExecutionResult,
    SQLMSSQLAdapterStatus,
)
from app.evaluation.mssql_connection_resolver import resolve_local_docker_connection


def _rows_to_dicts(
    rows: Tuple[Tuple[Any, ...], ...],
    columns: Tuple[str, ...],
) -> Tuple[Tuple[Mapping[str, Any], ...], Tuple[str, ...]]:
    dict_rows = []
    warnings: Tuple[str, ...] = ()
    mismatch = any(len(row) != len(columns) for row in rows)
    if mismatch or not columns:
        for row in rows:
            dict_rows.append({f"col_{i}": v for i, v in enumerate(row)})
        if rows and mismatch:
            warnings = ("column names unavailable or arity mismatch; used positional col_<i> keys",)
    else:
        for row in rows:
            dict_rows.append(dict(zip(columns, row)))
    return tuple(dict_rows), warnings


def normalize_mssql_execution_result(
    mssql: SQLMSSQLAdapterExecutionResult,
    request: SQLDatabaseExecutionRequest,
) -> SQLDatabaseExecutionResult:
    sql_sha256 = hashlib.sha256(request.sql.encode("utf-8")).hexdigest()

    if mssql.status == SQLMSSQLAdapterStatus.EXECUTED:
        dict_rows, extra_warnings = _rows_to_dicts(mssql.rows, mssql.columns)
        warnings = tuple(mssql.warnings) + extra_warnings
        return SQLDatabaseExecutionResult(
            version=SQL_MULTI_DATABASE_EXECUTION_VERSION,
            case_id=request.case_id,
            dialect=SQLDatabaseDialect.SQLSERVER,
            sql=request.sql,
            sql_sha256=sql_sha256,
            rows=dict_rows,
            row_count=len(dict_rows),
            truncated=mssql.truncated,
            execution_error=None,
            duration_ms=mssql.duration_ms,
            warnings=warnings,
        )

    return SQLDatabaseExecutionResult(
        version=SQL_MULTI_DATABASE_EXECUTION_VERSION,
        case_id=request.case_id,
        dialect=SQLDatabaseDialect.SQLSERVER,
        sql=request.sql,
        sql_sha256=sql_sha256,
        rows=(),
        row_count=0,
        truncated=False,
        execution_error=mssql.error or f"SQL Server execution not completed ({mssql.status.value}).",
        duration_ms=mssql.duration_ms,
        warnings=tuple(mssql.warnings),
    )


def _to_mssql_config(config: SQLDatabaseExecutionConfig) -> SQLMSSQLAdapterConfig:
    return SQLMSSQLAdapterConfig(
        timeout_seconds=config.timeout_seconds,
        max_rows=config.max_rows,
        execution_mode=config.execution_mode.value,
    )


class MSSQLDatabaseExecutionAdapter(SQLDatabaseExecutionAdapter):
    """Local-Docker-only, read-only SQL Server execution adapter (Sprint 29.6).

    Resolves a local-Docker connection via the 29.6 resolver and delegates the
    real ``SELECT`` to the low-level SQL Server adapter, then normalizes to the
    shared result contract. No connection resolved -> graceful empty result with
    ``execution_error`` (never raises on that path). EXPLAIN-only mode is not
    supported (rejected) — deferred to a later sprint.
    """

    def __init__(self, connection_resolver=resolve_local_docker_connection):
        self._resolve = connection_resolver

    @property
    def dialect(self) -> SQLDatabaseDialect:
        return SQLDatabaseDialect.SQLSERVER

    def capabilities(self):
        return (
            SQLExecutionAdapterCapability.CONNECTION_REF,
            SQLExecutionAdapterCapability.READ_ONLY,
        )

    def execute(self, request: SQLDatabaseExecutionRequest) -> SQLDatabaseExecutionResult:
        if not isinstance(request, SQLDatabaseExecutionRequest):
            raise SQLMultiDatabaseExecutionContractError(
                "request must be a SQLDatabaseExecutionRequest"
            )
        if request.dialect != SQLDatabaseDialect.SQLSERVER:
            raise SQLMultiDatabaseExecutionContractError(
                "SQL Server adapter only supports SQLSERVER dialect requests"
            )
        if request.connection_ref is None:
            raise SQLMultiDatabaseExecutionContractError(
                "SQL Server adapter requires connection_ref"
            )
        if request.fixture_ref is not None:
            raise SQLMultiDatabaseExecutionContractError(
                "SQL Server adapter does not support fixture_ref"
            )
        if request.config.execution_mode != SQLExecutionMode.READ_ONLY:
            raise SQLMultiDatabaseExecutionContractError(
                "SQL Server EXPLAIN-only mode is not supported in this contract version"
            )

        connection = self._resolve()
        if connection is None:
            return SQLDatabaseExecutionResult(
                version=SQL_MULTI_DATABASE_EXECUTION_VERSION,
                case_id=request.case_id,
                dialect=SQLDatabaseDialect.SQLSERVER,
                sql=request.sql,
                sql_sha256=hashlib.sha256(request.sql.encode("utf-8")).hexdigest(),
                rows=(),
                row_count=0,
                truncated=False,
                execution_error="No local Docker SQL Server connection available",
                duration_ms=0.0,
                warnings=(),
            )

        mssql_config = _to_mssql_config(request.config)
        mssql_request = SQLMSSQLAdapterExecutionRequest(
            case_id=request.case_id,
            sql=request.sql,
            dialect="sqlserver",
            config=mssql_config,
            connection_ref=request.connection_ref,
        )
        mssql_result = SQLMSSQLAdapterContract(connection=connection).execute(mssql_request)
        return normalize_mssql_execution_result(mssql_result, request)
