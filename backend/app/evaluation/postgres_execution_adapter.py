"""Sprint 29.1 — PostgreSQL Read-Only Execution adapter.

Bridges the Sprint 25.8 local-Docker read-only adapter to the dialect-agnostic
execution contract (``multi_database_execution``). Local-Docker-only, read-only,
side-effect-free. Driver-isolated: importing this module loads NO database driver
or network client; ``psycopg2`` is imported lazily only inside the 25.8 adapter's
real execution path.
"""

import hashlib
from typing import Any, Dict, Mapping, Optional, Tuple

from app.evaluation.multi_database_execution import (
    SQL_MULTI_DATABASE_EXECUTION_VERSION,
    SQLDatabaseDialect,
    SQLDatabaseExecutionRequest,
    SQLDatabaseExecutionResult,
)
from app.evaluation.postgres_adapter import (
    SQLPostgresAdapterExecutionResult,
    SQLPostgresAdapterStatus,
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
