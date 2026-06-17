import hashlib
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Optional, Tuple

SQL_POSTGRES_ADAPTER_CONTRACT_VERSION = "sql_postgres_adapter_contract_v1"


class SQLPostgresAdapterContractError(ValueError):
    """Raised when PostgreSQL adapter contract rules or configurations are violated."""
    pass


class SQLPostgresAdapterStatus(str, Enum):
    NOT_IMPLEMENTED = "not_implemented"
    REJECTED = "rejected"


@dataclass(frozen=True)
class SQLPostgresAdapterCapability:
    version: str
    dialect: str
    supports_live_execution: bool
    supports_driver_execution: bool
    supports_network_execution: bool
    supports_read_only_queries: bool

    def __post_init__(self):
        if self.version != SQL_POSTGRES_ADAPTER_CONTRACT_VERSION:
            raise SQLPostgresAdapterContractError(f"Invalid capability version: {self.version}")
        if self.dialect != "postgresql":
            raise SQLPostgresAdapterContractError(f"Dialect must be postgresql: {self.dialect}")
        if not isinstance(self.supports_live_execution, bool):
            raise SQLPostgresAdapterContractError("supports_live_execution must be a boolean")
        if not isinstance(self.supports_driver_execution, bool):
            raise SQLPostgresAdapterContractError("supports_driver_execution must be a boolean")
        if not isinstance(self.supports_network_execution, bool):
            raise SQLPostgresAdapterContractError("supports_network_execution must be a boolean")
        if not isinstance(self.supports_read_only_queries, bool):
            raise SQLPostgresAdapterContractError("supports_read_only_queries must be a boolean")


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
    error: Optional[str] = None
    warnings: Tuple[str, ...] = field(default_factory=tuple)
    duration_ms: float = 0.0

    def __post_init__(self):
        if self.version != SQL_POSTGRES_ADAPTER_CONTRACT_VERSION:
            raise SQLPostgresAdapterContractError(f"Invalid version: {self.version}")
        if not self.case_id or not isinstance(self.case_id, str) or not self.case_id.strip():
            raise SQLPostgresAdapterContractError("case_id cannot be empty")
        if not isinstance(self.status, SQLPostgresAdapterStatus):
            raise SQLPostgresAdapterContractError("Invalid status")
        
        import re
        if not self.sql_sha256 or not isinstance(self.sql_sha256, str) or not re.fullmatch(r"[a-f0-9]{64}", self.sql_sha256):
            raise SQLPostgresAdapterContractError("sql_sha256 must be a lowercase SHA-256 hex digest")
            
        if self.error is not None and not isinstance(self.error, str):
            raise SQLPostgresAdapterContractError("error must be a string or None")
        if not isinstance(self.warnings, tuple):
            raise SQLPostgresAdapterContractError("warnings must be a tuple")
        for w in self.warnings:
            if not isinstance(w, str):
                raise SQLPostgresAdapterContractError("All warnings must be strings")
        if not isinstance(self.duration_ms, (int, float)) or isinstance(self.duration_ms, bool) or self.duration_ms < 0:
            raise SQLPostgresAdapterContractError("duration_ms must be a non-negative number")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "version": self.version,
            "case_id": self.case_id,
            "status": self.status.value,
            "sql_sha256": self.sql_sha256,
            "error": self.error,
            "warnings": list(self.warnings),
            "duration_ms": self.duration_ms,
        }


class SQLPostgresAdapterContract:
    def __init__(self, capability: Optional[SQLPostgresAdapterCapability] = None):
        self._capability = capability or SQLPostgresAdapterCapability(
            version=SQL_POSTGRES_ADAPTER_CONTRACT_VERSION,
            dialect="postgresql",
            supports_live_execution=False,
            supports_driver_execution=False,
            supports_network_execution=False,
            supports_read_only_queries=False
        )

    @property
    def capability(self) -> SQLPostgresAdapterCapability:
        return self._capability

    def execute(self, request: SQLPostgresAdapterExecutionRequest) -> SQLPostgresAdapterExecutionResult:
        if not isinstance(request, SQLPostgresAdapterExecutionRequest):
            raise SQLPostgresAdapterContractError("request must be a SQLPostgresAdapterExecutionRequest")

        sql_hash = hashlib.sha256(request.sql.encode("utf-8")).hexdigest()

        return SQLPostgresAdapterExecutionResult(
            version=SQL_POSTGRES_ADAPTER_CONTRACT_VERSION,
            case_id=request.case_id,
            status=SQLPostgresAdapterStatus.NOT_IMPLEMENTED,
            sql_sha256=sql_hash,
            error="PostgreSQL execution is not implemented under this contract version.",
            warnings=(),
            duration_ms=0.0
        )
