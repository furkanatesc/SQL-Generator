"""Sprint 25.9 — Oracle Adapter Contract Stub.

Maturity: MVP / early beta. NOT production-ready. This sprint does NOT implement
real Oracle execution; it only locks the *contract* a real Oracle adapter must
obey later (the production implementation lands in Phase 10 — 29.3 adapter,
29.4 Docker/test-harness strategy).

Why Oracle stays a pure stub while PostgreSQL (25.8) already runs local-Docker
read-only queries: Oracle is higher risk. Different driver/licensing, separate
Docker/test-harness strategy, riskier DSN/TNS/wallet connection formats, and
enterprise Oracle environments that sit much closer to production. So 25.9 makes
*no* real-execution claim.

Hard boundaries enforced here (and locked by tests):

* Every execution capability flag is forced ``False`` — no live, driver, network,
  read-only, local-docker, remote, production, or Oracle execution is claimed.
* No Oracle driver (``cx_Oracle`` / ``oracledb``), no SQLAlchemy engine, no JDBC.
* No network / socket access, no DSN / TNS / wallet parsing.
* No environment-variable or secret-manager credential resolution.
* Results carry only ``sql_sha256`` — never raw SQL, connection refs, DSNs, or
  credentials.
* The default path is deterministic ``NOT_IMPLEMENTED``; unsafe input is
  deterministic ``REJECTED``.
"""

import hashlib
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Tuple

from app.security.sql_read_only_enforcement import (
    SQL_READ_ONLY_ENFORCEMENT_CONTRACT_VERSION,
    SQLReadOnlyDecision,
    SQLReadOnlyEnforcementContract,
    SQLReadOnlyEnforcementRequest,
)

SQL_ORACLE_ADAPTER_CONTRACT_VERSION = "sql_oracle_adapter_contract_v1"

# Sprint 26.2: like the PostgreSQL adapter, the read-only SELECT gate delegates to
# the shared, centrally-tested enforcement contract (app.security) so all adapters
# enforce identical read-only rules. The keyword/SELECT-only logic lives in one place.
_READ_ONLY_ENFORCER = SQLReadOnlyEnforcementContract()

_JSON_SAFE_TYPES = (type(None), bool, int, float, str)

# Every capability flag the stub exposes — all are enforced to ``False``.
_CAPABILITY_FLAGS = (
    "supports_live_execution",
    "supports_driver_execution",
    "supports_network_execution",
    "supports_read_only_queries",
    "supports_local_docker_execution",
    "supports_remote_execution",
    "supports_production_execution",
    "supports_oracle_execution",
)


class SQLOracleAdapterContractError(ValueError):
    """Raised when Oracle adapter contract rules or configurations are violated."""
    pass


class SQLOracleAdapterStatus(str, Enum):
    NOT_IMPLEMENTED = "not_implemented"
    REJECTED = "rejected"


@dataclass(frozen=True)
class SQLOracleAdapterCapability:
    """Describes what the Oracle adapter is allowed to do — in this sprint, nothing.

    Unlike the PostgreSQL 25.8 adapter (which exposes local-Docker read-only
    execution), the Oracle stub makes NO execution claim of any kind. Every flag
    is enforced to ``False``; a ``True`` on any flag is a contract violation. This
    keeps a prematurely-enabled Oracle driver, remote/production access, or
    credential resolution from slipping in before the real adapter (29.3) exists.
    """
    version: str
    dialect: str
    supports_live_execution: bool
    supports_driver_execution: bool
    supports_network_execution: bool
    supports_read_only_queries: bool
    supports_local_docker_execution: bool
    supports_remote_execution: bool
    supports_production_execution: bool
    supports_oracle_execution: bool

    def __post_init__(self):
        if self.version != SQL_ORACLE_ADAPTER_CONTRACT_VERSION:
            raise SQLOracleAdapterContractError(f"Invalid capability version: {self.version}")
        if self.dialect != "oracle":
            raise SQLOracleAdapterContractError(f"Dialect must be oracle: {self.dialect}")

        for name in _CAPABILITY_FLAGS:
            value = getattr(self, name)
            if not isinstance(value, bool):
                raise SQLOracleAdapterContractError(f"{name} must be a boolean")
            # Boundaries that can never be crossed in Sprint 25.9 (pure stub).
            if value is not False:
                raise SQLOracleAdapterContractError(
                    f"Oracle adapter contract stub cannot enable {name}; "
                    "real Oracle execution arrives in Phase 10 (29.3)"
                )


def default_oracle_stub_capability() -> SQLOracleAdapterCapability:
    """The fixed, all-disabled capability of the Sprint 25.9 Oracle stub."""
    return SQLOracleAdapterCapability(
        version=SQL_ORACLE_ADAPTER_CONTRACT_VERSION,
        dialect="oracle",
        supports_live_execution=False,
        supports_driver_execution=False,
        supports_network_execution=False,
        supports_read_only_queries=False,
        supports_local_docker_execution=False,
        supports_remote_execution=False,
        supports_production_execution=False,
        supports_oracle_execution=False,
    )


@dataclass(frozen=True)
class SQLOracleAdapterConfig:
    """Execution config shape the real adapter (29.3) will consume.

    Validated for forward-compatibility, but inert in this sprint: nothing is
    executed, so these values never reach a driver.
    """
    timeout_seconds: float = 2.0
    max_rows: int = 1000
    execution_mode: str = "read_only"

    def __post_init__(self):
        if not isinstance(self.timeout_seconds, (int, float)) or isinstance(self.timeout_seconds, bool) or self.timeout_seconds <= 0:
            raise SQLOracleAdapterContractError("timeout_seconds must be a positive number")
        if not isinstance(self.max_rows, int) or isinstance(self.max_rows, bool) or self.max_rows <= 0:
            raise SQLOracleAdapterContractError("max_rows must be a positive integer")
        if self.execution_mode not in {"read_only", "explain_only"}:
            raise SQLOracleAdapterContractError(f"Invalid execution_mode: {self.execution_mode}")


@dataclass(frozen=True)
class SQLOracleAdapterExecutionRequest:
    case_id: str
    sql: str
    dialect: str
    config: SQLOracleAdapterConfig = field(default_factory=SQLOracleAdapterConfig)
    connection_ref: Optional[str] = None

    def __post_init__(self):
        if not self.case_id or not isinstance(self.case_id, str) or not self.case_id.strip():
            raise SQLOracleAdapterContractError("case_id cannot be empty")
        if not self.sql or not isinstance(self.sql, str) or not self.sql.strip():
            raise SQLOracleAdapterContractError("sql cannot be empty")
        if self.dialect != "oracle":
            raise SQLOracleAdapterContractError(f"Dialect must be oracle: {self.dialect}")
        if not isinstance(self.config, SQLOracleAdapterConfig):
            raise SQLOracleAdapterContractError("config must be a SQLOracleAdapterConfig")
        if self.connection_ref is not None and (not isinstance(self.connection_ref, str) or not self.connection_ref.strip()):
            raise SQLOracleAdapterContractError("connection_ref must be a non-empty string or None")


@dataclass(frozen=True)
class SQLOracleAdapterExecutionResult:
    version: str
    case_id: str
    status: SQLOracleAdapterStatus
    sql_sha256: str
    rows: Tuple[Tuple[Any, ...], ...] = ()
    row_count: int = 0
    truncated: bool = False
    error: Optional[str] = None
    warnings: Tuple[str, ...] = field(default_factory=tuple)
    duration_ms: float = 0.0

    def __post_init__(self):
        if self.version != SQL_ORACLE_ADAPTER_CONTRACT_VERSION:
            raise SQLOracleAdapterContractError(f"Invalid version: {self.version}")
        if not self.case_id or not isinstance(self.case_id, str) or not self.case_id.strip():
            raise SQLOracleAdapterContractError("case_id cannot be empty")
        if not isinstance(self.status, SQLOracleAdapterStatus):
            raise SQLOracleAdapterContractError("Invalid status")

        if not self.sql_sha256 or not isinstance(self.sql_sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", self.sql_sha256):
            raise SQLOracleAdapterContractError("sql_sha256 must be a lowercase SHA-256 hex digest")

        if not isinstance(self.rows, tuple):
            raise SQLOracleAdapterContractError("rows must be a tuple")
        for row in self.rows:
            if not isinstance(row, tuple):
                raise SQLOracleAdapterContractError("each row must be a tuple")
            for value in row:
                if not isinstance(value, _JSON_SAFE_TYPES):
                    raise SQLOracleAdapterContractError("row values must be JSON-serializable scalars")
        if not isinstance(self.row_count, int) or isinstance(self.row_count, bool) or self.row_count < 0:
            raise SQLOracleAdapterContractError("row_count must be a non-negative integer")
        if not isinstance(self.truncated, bool):
            raise SQLOracleAdapterContractError("truncated must be a boolean")

        if self.error is not None and not isinstance(self.error, str):
            raise SQLOracleAdapterContractError("error must be a string or None")
        if not isinstance(self.warnings, tuple):
            raise SQLOracleAdapterContractError("warnings must be a tuple")
        for w in self.warnings:
            if not isinstance(w, str):
                raise SQLOracleAdapterContractError("All warnings must be strings")
        if not isinstance(self.duration_ms, (int, float)) or isinstance(self.duration_ms, bool) or self.duration_ms < 0:
            raise SQLOracleAdapterContractError("duration_ms must be a non-negative number")

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
            "duration_ms": self.duration_ms,
        }


def validate_read_only_select(sql: str) -> Optional[str]:
    """Return a rejection reason, or ``None`` if ``sql`` is an allowed single
    read-only query.

    Thin wrapper over the shared Sprint 26.2 read-only enforcement contract
    (``app.security.sql_read_only_enforcement``); kept for the adapter's
    ``Optional[str]`` reason convention and to lock the rejection contract the real
    Oracle adapter (29.3) will reuse. Behavior is the shared, centrally-tested
    classifier: single trailing ``;`` allowed, any other ``;`` is multi-statement,
    the statement must begin with ``SELECT`` (or a read-only ``WITH ... SELECT``),
    and no write/DDL/PL-SQL/data-movement keyword may appear in executable code
    (comments and string/identifier literals are stripped before scanning).
    """
    result = _READ_ONLY_ENFORCER.enforce(
        SQLReadOnlyEnforcementRequest(
            version=SQL_READ_ONLY_ENFORCEMENT_CONTRACT_VERSION,
            sql=sql,
            dialect="oracle",
        )
    )
    if result.decision == SQLReadOnlyDecision.ALLOW:
        return None
    return result.reason


class SQLOracleAdapterContract:
    """Oracle adapter contract stub.

    This adapter NEVER executes a query and has no connection path at all (no
    DSN, no wallet, no driver). It exists to lock the security / capability /
    result / rejection contract before any real Oracle connectivity (29.3) is
    built, so the orchestrator's default path can never gain Oracle execution.

    Behavior:

    * Unsafe input (non-``SELECT`` / multi-statement / write / DDL / PL-SQL) ->
      deterministic :attr:`SQLOracleAdapterStatus.REJECTED`.
    * Any other request -> deterministic :attr:`SQLOracleAdapterStatus.NOT_IMPLEMENTED`.
    """

    def __init__(self, capability: Optional[SQLOracleAdapterCapability] = None):
        if capability is not None and not isinstance(capability, SQLOracleAdapterCapability):
            raise SQLOracleAdapterContractError("capability must be a SQLOracleAdapterCapability")
        self._capability = capability or default_oracle_stub_capability()

    @property
    def capability(self) -> SQLOracleAdapterCapability:
        return self._capability

    def execute(self, request: SQLOracleAdapterExecutionRequest) -> SQLOracleAdapterExecutionResult:
        if not isinstance(request, SQLOracleAdapterExecutionRequest):
            raise SQLOracleAdapterContractError("request must be a SQLOracleAdapterExecutionRequest")

        sql_hash = hashlib.sha256(request.sql.encode("utf-8")).hexdigest()

        # Lock the rejection contract: unsafe input is rejected deterministically,
        # without any connection / driver / network access.
        reason = validate_read_only_select(request.sql)
        if reason is not None:
            return self._result(request, sql_hash, SQLOracleAdapterStatus.REJECTED, error=reason)

        # No real Oracle execution exists in this sprint -> inert NOT_IMPLEMENTED.
        return self._result(
            request, sql_hash, SQLOracleAdapterStatus.NOT_IMPLEMENTED,
            error="Oracle execution is not implemented under this contract version.",
        )

    def _result(
        self,
        request: SQLOracleAdapterExecutionRequest,
        sql_hash: str,
        status: SQLOracleAdapterStatus,
        *,
        error: Optional[str] = None,
        warnings: Tuple[str, ...] = (),
    ) -> SQLOracleAdapterExecutionResult:
        return SQLOracleAdapterExecutionResult(
            version=SQL_ORACLE_ADAPTER_CONTRACT_VERSION,
            case_id=request.case_id,
            status=status,
            sql_sha256=sql_hash,
            rows=(),
            row_count=0,
            truncated=False,
            error=error,
            warnings=tuple(warnings),
            duration_ms=0.0,
        )
