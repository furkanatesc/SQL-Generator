"""Sprint 25.8 — PostgreSQL Read-Only Adapter (Local Docker Only).

Maturity: MVP / early beta. NOT production-ready.

This adapter takes the Sprint 25.7 contract stub one step further: it can execute
real ``SELECT`` queries, but ONLY against a local Docker PostgreSQL instance and
ONLY in read-only mode. Hard boundaries (enforced here, never crossed):

* No production / remote database — connections are restricted to local Docker
  hosts (localhost / 127.0.0.1 / ::1) and the ``local_docker`` environment.
* No user-provided connection string — connection params come from a controlled
  ``SQLPostgresLocalDockerConnection`` object, never from the request SQL.
* No secret manager / env-var secret loading at import time.
* SELECT-only, single-statement queries; writes / DDL / DML are rejected.
* The database driver is imported lazily, only on the real execution path.
"""

import hashlib
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from app.security.sql_read_only_enforcement import (
    SQL_READ_ONLY_ENFORCEMENT_CONTRACT_VERSION,
    SQLReadOnlyDecision,
    SQLReadOnlyEnforcementContract,
    SQLReadOnlyEnforcementRequest,
)

SQL_POSTGRES_ADAPTER_CONTRACT_VERSION = "sql_postgres_adapter_contract_v1"

# Hosts treated as "local Docker". Anything else is considered remote and rejected.
_LOCAL_DOCKER_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

# Sprint 26.2: the read-only SELECT gate is no longer adapter-local — it delegates
# to the shared, centrally-tested enforcement contract (app.security). This module
# keeps the same string-level pre-execution guard behavior; the keyword/SELECT-only
# rules now live in exactly one place.
_READ_ONLY_ENFORCER = SQLReadOnlyEnforcementContract()

_JSON_SAFE_TYPES = (type(None), bool, int, float, str)


class SQLPostgresAdapterContractError(ValueError):
    """Raised when PostgreSQL adapter contract rules or configurations are violated."""
    pass


class SQLPostgresAdapterStatus(str, Enum):
    NOT_IMPLEMENTED = "not_implemented"
    REJECTED = "rejected"
    EXECUTED = "executed"
    EXECUTION_ERROR = "execution_error"


@dataclass(frozen=True)
class SQLPostgresAdapterCapability:
    """Describes what the local-Docker read-only adapter is allowed to do.

    Safety-critical flags (``supports_live_execution``, ``supports_remote_execution``,
    ``supports_production_execution``) can NEVER be enabled in this sprint and are
    enforced to ``False``. The read-only / local-Docker flags are fixed ``True``
    because this adapter *is* the local-Docker read-only adapter.
    """
    version: str
    dialect: str
    supports_live_execution: bool          # production "live" execution — must stay False
    supports_driver_execution: bool        # real DB driver — True
    supports_network_execution: bool       # local Docker TCP only — True
    supports_read_only_queries: bool       # SELECT-only — True
    supports_local_docker_execution: bool  # True
    supports_remote_execution: bool        # must stay False
    supports_production_execution: bool    # must stay False

    def __post_init__(self):
        if self.version != SQL_POSTGRES_ADAPTER_CONTRACT_VERSION:
            raise SQLPostgresAdapterContractError(f"Invalid capability version: {self.version}")
        if self.dialect != "postgresql":
            raise SQLPostgresAdapterContractError(f"Dialect must be postgresql: {self.dialect}")

        for name in (
            "supports_live_execution", "supports_driver_execution",
            "supports_network_execution", "supports_read_only_queries",
            "supports_local_docker_execution", "supports_remote_execution",
            "supports_production_execution",
        ):
            if not isinstance(getattr(self, name), bool):
                raise SQLPostgresAdapterContractError(f"{name} must be a boolean")

        # Boundaries that can never be crossed in Sprint 25.8.
        if self.supports_live_execution is not False:
            raise SQLPostgresAdapterContractError(
                "PostgreSQL adapter cannot support production live execution"
            )
        if self.supports_remote_execution is not False:
            raise SQLPostgresAdapterContractError(
                "PostgreSQL adapter cannot support remote execution"
            )
        if self.supports_production_execution is not False:
            raise SQLPostgresAdapterContractError(
                "PostgreSQL adapter cannot support production execution"
            )

        # The local-Docker read-only capabilities this adapter must expose.
        if self.supports_local_docker_execution is not True:
            raise SQLPostgresAdapterContractError(
                "PostgreSQL adapter must support local Docker execution"
            )
        if self.supports_driver_execution is not True:
            raise SQLPostgresAdapterContractError(
                "PostgreSQL adapter must support driver execution"
            )
        if self.supports_read_only_queries is not True:
            raise SQLPostgresAdapterContractError(
                "PostgreSQL adapter must support read-only query execution"
            )
        if self.supports_network_execution is not True:
            raise SQLPostgresAdapterContractError(
                "PostgreSQL adapter must support (local Docker) network execution"
            )


def default_local_docker_capability() -> SQLPostgresAdapterCapability:
    """The fixed capability of the Sprint 25.8 local-Docker read-only adapter."""
    return SQLPostgresAdapterCapability(
        version=SQL_POSTGRES_ADAPTER_CONTRACT_VERSION,
        dialect="postgresql",
        supports_live_execution=False,
        supports_driver_execution=True,
        supports_network_execution=True,
        supports_read_only_queries=True,
        supports_local_docker_execution=True,
        supports_remote_execution=False,
        supports_production_execution=False,
    )


@dataclass(frozen=True)
class SQLPostgresLocalDockerConnection:
    """A controlled, local-Docker-only PostgreSQL connection config.

    This is the ONLY way to give the adapter a live connection. It refuses remote
    hosts and any non-``local_docker`` environment, so there is no path to a
    production or user-supplied database.
    """
    host: str
    port: int
    dbname: str
    user: str
    password: str = ""
    environment: str = "local_docker"

    def __post_init__(self):
        if self.environment != "local_docker":
            raise SQLPostgresAdapterContractError(
                "Only the 'local_docker' environment is allowed; "
                "remote/production environments are forbidden"
            )
        if not isinstance(self.host, str) or self.host not in _LOCAL_DOCKER_HOSTS:
            raise SQLPostgresAdapterContractError(
                "Only local Docker hosts are allowed "
                "(localhost / 127.0.0.1 / ::1); remote hosts are forbidden"
            )
        if not isinstance(self.port, int) or isinstance(self.port, bool) or not (1 <= self.port <= 65535):
            raise SQLPostgresAdapterContractError("port must be an integer in 1..65535")
        if not isinstance(self.dbname, str) or not self.dbname.strip():
            raise SQLPostgresAdapterContractError("dbname cannot be empty")
        if not isinstance(self.user, str) or not self.user.strip():
            raise SQLPostgresAdapterContractError("user cannot be empty")
        if not isinstance(self.password, str):
            raise SQLPostgresAdapterContractError("password must be a string")


@dataclass(frozen=True)
class SQLPostgresAdapterConfig:
    timeout_seconds: float = 2.0
    max_rows: int = 1000
    execution_mode: str = "read_only"

    def __post_init__(self):
        if not isinstance(self.timeout_seconds, (int, float)) or isinstance(self.timeout_seconds, bool) or self.timeout_seconds <= 0:
            raise SQLPostgresAdapterContractError("timeout_seconds must be a positive number")
        if not isinstance(self.max_rows, int) or isinstance(self.max_rows, bool) or self.max_rows <= 0:
            raise SQLPostgresAdapterContractError("max_rows must be a positive integer")
        if self.execution_mode not in {"read_only", "explain_only"}:
            raise SQLPostgresAdapterContractError(f"Invalid execution_mode: {self.execution_mode}")


@dataclass(frozen=True)
class SQLPostgresAdapterExecutionRequest:
    case_id: str
    sql: str
    dialect: str
    config: SQLPostgresAdapterConfig
    connection_ref: Optional[str] = None

    def __post_init__(self):
        if not self.case_id or not isinstance(self.case_id, str) or not self.case_id.strip():
            raise SQLPostgresAdapterContractError("case_id cannot be empty")
        if not self.sql or not isinstance(self.sql, str) or not self.sql.strip():
            raise SQLPostgresAdapterContractError("sql cannot be empty")
        if self.dialect != "postgresql":
            raise SQLPostgresAdapterContractError(f"Dialect must be postgresql: {self.dialect}")
        if not isinstance(self.config, SQLPostgresAdapterConfig):
            raise SQLPostgresAdapterContractError("config must be a SQLPostgresAdapterConfig")
        if self.connection_ref is not None and (not isinstance(self.connection_ref, str) or not self.connection_ref.strip()):
            raise SQLPostgresAdapterContractError("connection_ref must be a non-empty string or None")


@dataclass(frozen=True)
class SQLPostgresAdapterExecutionResult:
    version: str
    case_id: str
    status: SQLPostgresAdapterStatus
    sql_sha256: str
    rows: Tuple[Tuple[Any, ...], ...] = ()
    row_count: int = 0
    truncated: bool = False
    error: Optional[str] = None
    warnings: Tuple[str, ...] = field(default_factory=tuple)
    duration_ms: float = 0.0
    columns: Tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self):
        if self.version != SQL_POSTGRES_ADAPTER_CONTRACT_VERSION:
            raise SQLPostgresAdapterContractError(f"Invalid version: {self.version}")
        if not self.case_id or not isinstance(self.case_id, str) or not self.case_id.strip():
            raise SQLPostgresAdapterContractError("case_id cannot be empty")
        if not isinstance(self.status, SQLPostgresAdapterStatus):
            raise SQLPostgresAdapterContractError("Invalid status")

        if not self.sql_sha256 or not isinstance(self.sql_sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", self.sql_sha256):
            raise SQLPostgresAdapterContractError("sql_sha256 must be a lowercase SHA-256 hex digest")

        if not isinstance(self.rows, tuple):
            raise SQLPostgresAdapterContractError("rows must be a tuple")
        for row in self.rows:
            if not isinstance(row, tuple):
                raise SQLPostgresAdapterContractError("each row must be a tuple")
            for value in row:
                if not isinstance(value, _JSON_SAFE_TYPES):
                    raise SQLPostgresAdapterContractError("row values must be JSON-serializable scalars")
        if not isinstance(self.row_count, int) or isinstance(self.row_count, bool) or self.row_count < 0:
            raise SQLPostgresAdapterContractError("row_count must be a non-negative integer")
        if not isinstance(self.truncated, bool):
            raise SQLPostgresAdapterContractError("truncated must be a boolean")

        if self.error is not None and not isinstance(self.error, str):
            raise SQLPostgresAdapterContractError("error must be a string or None")
        if not isinstance(self.warnings, tuple):
            raise SQLPostgresAdapterContractError("warnings must be a tuple")
        for w in self.warnings:
            if not isinstance(w, str):
                raise SQLPostgresAdapterContractError("All warnings must be strings")
        if not isinstance(self.duration_ms, (int, float)) or isinstance(self.duration_ms, bool) or self.duration_ms < 0:
            raise SQLPostgresAdapterContractError("duration_ms must be a non-negative number")

        if not isinstance(self.columns, tuple):
            raise SQLPostgresAdapterContractError("columns must be a tuple")
        for c in self.columns:
            if not isinstance(c, str):
                raise SQLPostgresAdapterContractError("All columns must be strings")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "case_id": self.case_id,
            "status": self.status.value,
            "sql_sha256": self.sql_sha256,
            "rows": [list(row) for row in self.rows],
            "row_count": self.row_count,
            "truncated": self.truncated,
            "error": self.error,
            "warnings": list(self.warnings),
            "columns": list(self.columns),
            "duration_ms": self.duration_ms,
        }


def validate_read_only_select(sql: str) -> Optional[str]:
    """Return a rejection reason, or ``None`` if ``sql`` is an allowed single
    read-only query.

    Thin wrapper over the shared Sprint 26.2 read-only enforcement contract
    (``app.security.sql_read_only_enforcement``); kept for backward compatibility
    with the adapter's ``Optional[str]`` reason convention. Behavior is the shared,
    centrally-tested classifier: a single trailing semicolon is allowed, any other
    ``;`` is multi-statement, the statement must begin with ``SELECT`` (or a
    read-only ``WITH ... SELECT``), and no write/DDL/procedure/data-movement
    keyword may appear — matched even inside string literals (conservative, safe).
    """
    result = _READ_ONLY_ENFORCER.enforce(
        SQLReadOnlyEnforcementRequest(
            version=SQL_READ_ONLY_ENFORCEMENT_CONTRACT_VERSION,
            sql=sql,
            dialect="postgresql",
        )
    )
    if result.decision == SQLReadOnlyDecision.ALLOW:
        return None
    return result.reason


def _normalize_value(value: Any) -> Any:
    if isinstance(value, _JSON_SAFE_TYPES):
        return value
    return str(value)


def _normalize_row(row: Any) -> Tuple[Any, ...]:
    return tuple(_normalize_value(v) for v in row)


def _sanitize_db_error(exc: Exception) -> str:
    """Credential-free, deterministic error message.

    Never includes the raw driver message, host, user, password, or connection
    ref — those can leak connection details. Timeouts get a distinct message.
    """
    pgcode = getattr(exc, "pgcode", None)
    if pgcode == "57014":  # query_canceled (statement_timeout)
        return "PostgreSQL execution timed out (statement_timeout exceeded)."
    return f"PostgreSQL execution failed ({type(exc).__name__})."


class SQLPostgresAdapterContract:
    """Local-Docker-only, read-only PostgreSQL adapter.

    With no ``connection`` wired the adapter stays inert (returns
    ``NOT_IMPLEMENTED``), so the orchestrator's default path does not gain live
    execution. A real execution path opens only when constructed with a valid
    :class:`SQLPostgresLocalDockerConnection`.
    """

    def __init__(
        self,
        capability: Optional[SQLPostgresAdapterCapability] = None,
        connection: Optional[SQLPostgresLocalDockerConnection] = None,
    ):
        if capability is not None and not isinstance(capability, SQLPostgresAdapterCapability):
            raise SQLPostgresAdapterContractError("capability must be a SQLPostgresAdapterCapability")
        if connection is not None and not isinstance(connection, SQLPostgresLocalDockerConnection):
            raise SQLPostgresAdapterContractError("connection must be a SQLPostgresLocalDockerConnection")
        self._capability = capability or default_local_docker_capability()
        self._connection = connection

    @property
    def capability(self) -> SQLPostgresAdapterCapability:
        return self._capability

    def execute(self, request: SQLPostgresAdapterExecutionRequest) -> SQLPostgresAdapterExecutionResult:
        if not isinstance(request, SQLPostgresAdapterExecutionRequest):
            raise SQLPostgresAdapterContractError("request must be a SQLPostgresAdapterExecutionRequest")

        sql_hash = hashlib.sha256(request.sql.encode("utf-8")).hexdigest()

        # No connection wired -> inert stub (orchestrator default path stays disabled).
        if self._connection is None:
            return self._result(
                request, sql_hash, SQLPostgresAdapterStatus.NOT_IMPLEMENTED,
                error="No local Docker PostgreSQL connection configured; execution is disabled.",
            )

        # Defense layer 1: string-level read-only SELECT gate.
        reason = validate_read_only_select(request.sql)
        if reason is not None:
            return self._result(request, sql_hash, SQLPostgresAdapterStatus.REJECTED, error=reason)

        return self._execute_select(request, sql_hash)

    def _result(
        self,
        request: SQLPostgresAdapterExecutionRequest,
        sql_hash: str,
        status: SQLPostgresAdapterStatus,
        *,
        rows: Tuple[Tuple[Any, ...], ...] = (),
        row_count: int = 0,
        truncated: bool = False,
        columns: Tuple[str, ...] = (),
        error: Optional[str] = None,
        warnings: Tuple[str, ...] = (),
        duration_ms: float = 0.0,
    ) -> SQLPostgresAdapterExecutionResult:
        return SQLPostgresAdapterExecutionResult(
            version=SQL_POSTGRES_ADAPTER_CONTRACT_VERSION,
            case_id=request.case_id,
            status=status,
            sql_sha256=sql_hash,
            rows=rows,
            row_count=row_count,
            truncated=truncated,
            columns=tuple(columns),
            error=error,
            warnings=tuple(warnings),
            duration_ms=duration_ms,
        )

    def _execute_select(
        self, request: SQLPostgresAdapterExecutionRequest, sql_hash: str
    ) -> SQLPostgresAdapterExecutionResult:
        # Defense layer 2: lazy driver import (module import stays driver-free).
        try:
            import psycopg2  # noqa: WPS433 - runtime-only import is intentional
        except ImportError:
            return self._result(
                request, sql_hash, SQLPostgresAdapterStatus.EXECUTION_ERROR,
                error="PostgreSQL driver (psycopg2) is not available.",
            )

        conn = self._connection
        config = request.config
        max_rows = config.max_rows
        statement_timeout_ms = max(1, int(config.timeout_seconds * 1000))
        connect_timeout_s = max(1, int(round(config.timeout_seconds)))

        started = time.monotonic()
        db = None
        try:
            db = psycopg2.connect(
                host=conn.host,
                port=conn.port,
                dbname=conn.dbname,
                user=conn.user,
                password=conn.password,
                connect_timeout=connect_timeout_s,
                # Defense layer 3: DB-enforced read-only + statement timeout.
                options=f"-c statement_timeout={statement_timeout_ms} -c default_transaction_read_only=on",
            )
            db.set_session(readonly=True, autocommit=False)
            with db.cursor() as cur:
                cur.execute(request.sql)
                fetched = cur.fetchmany(max_rows + 1)
                description = cur.description
            db.rollback()

            columns = tuple(d[0] for d in description) if description else ()
            truncated = len(fetched) > max_rows
            rows = tuple(_normalize_row(r) for r in fetched[:max_rows])
            duration_ms = (time.monotonic() - started) * 1000.0
            warnings = ("result truncated to max_rows",) if truncated else ()
            return self._result(
                request, sql_hash, SQLPostgresAdapterStatus.EXECUTED,
                rows=rows, row_count=len(rows), truncated=truncated,
                columns=columns, warnings=warnings, duration_ms=duration_ms,
            )
        except Exception as exc:  # noqa: BLE001 - must never leak connection details
            duration_ms = (time.monotonic() - started) * 1000.0
            return self._result(
                request, sql_hash, SQLPostgresAdapterStatus.EXECUTION_ERROR,
                error=_sanitize_db_error(exc), duration_ms=duration_ms,
            )
        finally:
            if db is not None:
                try:
                    db.close()
                except Exception:  # noqa: BLE001 - best-effort cleanup
                    pass
