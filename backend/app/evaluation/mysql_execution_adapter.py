"""Sprint 29.5 — MySQL Read-Only Execution adapter (bridge).

Bridges the Sprint 29.5 local-Docker read-only MySQL adapter to the
dialect-agnostic execution contract. Local-Docker-only, read-only,
side-effect-free. Driver-isolated: importing this module loads NO database
driver; ``pymysql`` is imported lazily only inside the low-level adapter's
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
from app.evaluation.mysql_adapter import (
    SQLMySQLAdapterConfig,
    SQLMySQLAdapterContract,
    SQLMySQLAdapterExecutionRequest,
    SQLMySQLAdapterExecutionResult,
    SQLMySQLAdapterStatus,
)
from app.evaluation.mysql_connection_resolver import resolve_local_docker_connection


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


def normalize_mysql_execution_result(
    mysql: SQLMySQLAdapterExecutionResult,
    request: SQLDatabaseExecutionRequest,
) -> SQLDatabaseExecutionResult:
    sql_sha256 = hashlib.sha256(request.sql.encode("utf-8")).hexdigest()

    if mysql.status == SQLMySQLAdapterStatus.EXECUTED:
        dict_rows, extra_warnings = _rows_to_dicts(mysql.rows, mysql.columns)
        warnings = tuple(mysql.warnings) + extra_warnings
        return SQLDatabaseExecutionResult(
            version=SQL_MULTI_DATABASE_EXECUTION_VERSION,
            case_id=request.case_id,
            dialect=SQLDatabaseDialect.MYSQL,
            sql=request.sql,
            sql_sha256=sql_sha256,
            rows=dict_rows,
            row_count=len(dict_rows),
            truncated=mysql.truncated,
            execution_error=None,
            duration_ms=mysql.duration_ms,
            warnings=warnings,
        )

    return SQLDatabaseExecutionResult(
        version=SQL_MULTI_DATABASE_EXECUTION_VERSION,
        case_id=request.case_id,
        dialect=SQLDatabaseDialect.MYSQL,
        sql=request.sql,
        sql_sha256=sql_sha256,
        rows=(),
        row_count=0,
        truncated=False,
        execution_error=mysql.error or f"MySQL execution not completed ({mysql.status.value}).",
        duration_ms=mysql.duration_ms,
        warnings=tuple(mysql.warnings),
    )


def _to_mysql_config(config: SQLDatabaseExecutionConfig) -> SQLMySQLAdapterConfig:
    return SQLMySQLAdapterConfig(
        timeout_seconds=config.timeout_seconds,
        max_rows=config.max_rows,
        execution_mode=config.execution_mode.value,
    )


class MySQLDatabaseExecutionAdapter(SQLDatabaseExecutionAdapter):
    """Local-Docker-only, read-only MySQL execution adapter (Sprint 29.5).

    Resolves a local-Docker connection via the 29.5 resolver and delegates the
    real ``SELECT`` to the low-level MySQL adapter, then normalizes to the
    shared result contract. No connection resolved -> graceful empty result with
    ``execution_error`` (never raises on that path). EXPLAIN-only mode is not
    supported (rejected) — deferred to a later sprint.
    """

    def __init__(self, connection_resolver=resolve_local_docker_connection):
        self._resolve = connection_resolver

    @property
    def dialect(self) -> SQLDatabaseDialect:
        return SQLDatabaseDialect.MYSQL

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
        if request.dialect != SQLDatabaseDialect.MYSQL:
            raise SQLMultiDatabaseExecutionContractError(
                "MySQL adapter only supports MYSQL dialect requests"
            )
        if request.connection_ref is None:
            raise SQLMultiDatabaseExecutionContractError(
                "MySQL adapter requires connection_ref"
            )
        if request.fixture_ref is not None:
            raise SQLMultiDatabaseExecutionContractError(
                "MySQL adapter does not support fixture_ref"
            )
        if request.config.execution_mode != SQLExecutionMode.READ_ONLY:
            raise SQLMultiDatabaseExecutionContractError(
                "MySQL EXPLAIN-only mode is not supported in this contract version"
            )

        connection = self._resolve()
        if connection is None:
            return SQLDatabaseExecutionResult(
                version=SQL_MULTI_DATABASE_EXECUTION_VERSION,
                case_id=request.case_id,
                dialect=SQLDatabaseDialect.MYSQL,
                sql=request.sql,
                sql_sha256=hashlib.sha256(request.sql.encode("utf-8")).hexdigest(),
                rows=(),
                row_count=0,
                truncated=False,
                execution_error="No local Docker MySQL connection available",
                duration_ms=0.0,
                warnings=(),
            )

        mysql_config = _to_mysql_config(request.config)
        mysql_request = SQLMySQLAdapterExecutionRequest(
            case_id=request.case_id,
            sql=request.sql,
            dialect="mysql",
            config=mysql_config,
            connection_ref=request.connection_ref,
        )
        mysql_result = SQLMySQLAdapterContract(connection=connection).execute(mysql_request)
        return normalize_mysql_execution_result(mysql_result, request)
