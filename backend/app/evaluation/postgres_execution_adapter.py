"""Sprint 29.1 — PostgreSQL Read-Only Execution adapter.

Bridges the Sprint 25.8 local-Docker read-only adapter to the dialect-agnostic
execution contract (``multi_database_execution``). Local-Docker-only, read-only,
side-effect-free. Driver-isolated: importing this module loads NO database driver
or network client; ``psycopg2`` is imported lazily only inside the 25.8 adapter's
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
from app.evaluation.postgres_adapter import (
    SQLPostgresAdapterConfig,
    SQLPostgresAdapterContract,
    SQLPostgresAdapterExecutionRequest,
    SQLPostgresAdapterExecutionResult,
    SQLPostgresAdapterStatus,
)
from app.evaluation.postgres_connection_resolver import (
    resolve_local_docker_connection,
)


def _rows_to_dicts(
    rows: Tuple[Tuple[Any, ...], ...],
    columns: Tuple[str, ...],
) -> Tuple[Tuple[Mapping[str, Any], ...], Tuple[str, ...]]:
    """Map positional rows to dict rows using ``columns``.

    Returns (dict_rows, extra_warnings). If any row's arity does not match
    ``columns``, falls back to positional ``col_<i>`` keys and emits a warning
    (never silently drops data).
    """
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


def normalize_postgres_execution_result(
    pg: SQLPostgresAdapterExecutionResult,
    request: SQLDatabaseExecutionRequest,
) -> SQLDatabaseExecutionResult:
    """Normalize a Sprint 25.8 adapter result into the shared execution contract."""
    sql_sha256 = hashlib.sha256(request.sql.encode("utf-8")).hexdigest()

    if pg.status == SQLPostgresAdapterStatus.EXECUTED:
        dict_rows, extra_warnings = _rows_to_dicts(pg.rows, pg.columns)
        warnings = tuple(pg.warnings) + extra_warnings
        return SQLDatabaseExecutionResult(
            version=SQL_MULTI_DATABASE_EXECUTION_VERSION,
            case_id=request.case_id,
            dialect=SQLDatabaseDialect.POSTGRESQL,
            sql=request.sql,
            sql_sha256=sql_sha256,
            rows=dict_rows,
            row_count=len(dict_rows),
            truncated=pg.truncated,
            execution_error=None,
            duration_ms=pg.duration_ms,
            warnings=warnings,
        )

    return SQLDatabaseExecutionResult(
        version=SQL_MULTI_DATABASE_EXECUTION_VERSION,
        case_id=request.case_id,
        dialect=SQLDatabaseDialect.POSTGRESQL,
        sql=request.sql,
        sql_sha256=sql_sha256,
        rows=(),
        row_count=0,
        truncated=False,
        execution_error=pg.error or f"PostgreSQL execution not completed ({pg.status.value}).",
        duration_ms=pg.duration_ms,
        warnings=tuple(pg.warnings),
    )


def _to_pg_config(config: SQLDatabaseExecutionConfig) -> SQLPostgresAdapterConfig:
    """Map the shared execution config to the Sprint 25.8 adapter config."""
    return SQLPostgresAdapterConfig(
        timeout_seconds=config.timeout_seconds,
        max_rows=config.max_rows,
        execution_mode=config.execution_mode.value,
        explain_analyze=config.explain_analyze,
    )


class PostgresDatabaseExecutionAdapter(SQLDatabaseExecutionAdapter):
    """Local-Docker-only, read-only PostgreSQL execution adapter (Sprint 29.1).

    Resolves a local-Docker connection via the Sprint 29.0 resolver and delegates
    the real ``SELECT`` to the Sprint 25.8 adapter, then normalizes the result to
    the shared ``SQLDatabaseExecutionResult`` contract. No connection resolved
    (no local Docker) -> graceful empty result with ``execution_error`` (never
    raises on that path), matching the inert-by-default posture of 25.8/29.0.
    """

    def __init__(self, connection_resolver=resolve_local_docker_connection):
        self._resolve = connection_resolver

    @property
    def dialect(self) -> SQLDatabaseDialect:
        return SQLDatabaseDialect.POSTGRESQL

    def capabilities(self):
        return (
            SQLExecutionAdapterCapability.CONNECTION_REF,
            SQLExecutionAdapterCapability.READ_ONLY,
            SQLExecutionAdapterCapability.EXPLAIN_ONLY,
        )

    def execute(self, request: SQLDatabaseExecutionRequest) -> SQLDatabaseExecutionResult:
        if not isinstance(request, SQLDatabaseExecutionRequest):
            raise SQLMultiDatabaseExecutionContractError(
                "request must be a SQLDatabaseExecutionRequest"
            )
        if request.dialect != SQLDatabaseDialect.POSTGRESQL:
            raise SQLMultiDatabaseExecutionContractError(
                "PostgreSQL adapter only supports POSTGRESQL dialect requests"
            )
        if request.connection_ref is None:
            raise SQLMultiDatabaseExecutionContractError(
                "PostgreSQL adapter requires connection_ref"
            )
        if request.fixture_ref is not None:
            raise SQLMultiDatabaseExecutionContractError(
                "PostgreSQL adapter does not support fixture_ref"
            )
        if request.config.execution_mode not in (
            SQLExecutionMode.READ_ONLY, SQLExecutionMode.EXPLAIN_ONLY
        ):
            raise SQLMultiDatabaseExecutionContractError(
                "PostgreSQL adapter supports only read_only or explain_only execution mode"
            )

        connection = self._resolve()
        if connection is None:
            return SQLDatabaseExecutionResult(
                version=SQL_MULTI_DATABASE_EXECUTION_VERSION,
                case_id=request.case_id,
                dialect=SQLDatabaseDialect.POSTGRESQL,
                sql=request.sql,
                sql_sha256=hashlib.sha256(request.sql.encode("utf-8")).hexdigest(),
                rows=(),
                row_count=0,
                truncated=False,
                execution_error="No local Docker PostgreSQL connection available",
                duration_ms=0.0,
                warnings=(),
            )

        pg_config = _to_pg_config(request.config)
        pg_request = SQLPostgresAdapterExecutionRequest(
            case_id=request.case_id,
            sql=request.sql,
            dialect="postgresql",
            config=pg_config,
            connection_ref=request.connection_ref,
        )
        pg_result = SQLPostgresAdapterContract(connection=connection).execute(pg_request)
        return normalize_postgres_execution_result(pg_result, request)
