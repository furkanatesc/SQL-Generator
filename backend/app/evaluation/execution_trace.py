import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple

SQL_EXECUTION_TRACE_VERSION = "sql_execution_trace_v1"


class SQLExecutionTraceContractError(ValueError):
    """Raised when execution trace contract rules or argument types are violated."""
    pass


@dataclass(frozen=True)
class SQLExecutionTraceRecord:
    version: str
    case_id: str
    dialect: str
    execution_mode: str
    has_fixture_ref: bool
    has_connection_ref: bool
    sql_sha256: str
    plan_status: str  # "planned", "no_plan"
    outcome_status: str  # "executed", "blocked_live_connection", "rejected"
    warnings: Tuple[str, ...] = field(default_factory=tuple)
    failure_category: Optional[str] = None
    duration_ms: Optional[float] = None
    error: Optional[str] = None

    def __post_init__(self):
        if self.version != SQL_EXECUTION_TRACE_VERSION:
            raise SQLExecutionTraceContractError(f"Invalid trace version: {self.version}")
        
        # Validation checks to enforce strict contract boundaries
        if not self.case_id or not isinstance(self.case_id, str) or not self.case_id.strip():
            raise SQLExecutionTraceContractError("case_id cannot be empty")
        if not self.dialect or not isinstance(self.dialect, str) or not self.dialect.strip():
            raise SQLExecutionTraceContractError("dialect cannot be empty")
        if not self.execution_mode or not isinstance(self.execution_mode, str) or not self.execution_mode.strip():
            raise SQLExecutionTraceContractError("execution_mode cannot be empty")
        if not isinstance(self.has_fixture_ref, bool):
            raise SQLExecutionTraceContractError("has_fixture_ref must be a boolean")
        if not isinstance(self.has_connection_ref, bool):
            raise SQLExecutionTraceContractError("has_connection_ref must be a boolean")
        if not self.sql_sha256 or not isinstance(self.sql_sha256, str) or not self.sql_sha256.strip():
            raise SQLExecutionTraceContractError("sql_sha256 cannot be empty")
        if not self.plan_status or not isinstance(self.plan_status, str) or not self.plan_status.strip():
            raise SQLExecutionTraceContractError("plan_status cannot be empty")
        if not self.outcome_status or not isinstance(self.outcome_status, str) or not self.outcome_status.strip():
            raise SQLExecutionTraceContractError("outcome_status cannot be empty")
        if not isinstance(self.warnings, tuple):
            raise SQLExecutionTraceContractError("warnings must be a tuple")

    @classmethod
    def from_outcome(
        cls,
        outcome: Any,
        failure_category: Optional[str] = None,
        duration_ms: Optional[float] = None
    ) -> "SQLExecutionTraceRecord":
        """Maps SQLConnectionAwareExecutionOutcome to an immutable trace record."""
        from app.evaluation.connection_aware_execution_orchestrator import SQLConnectionAwareExecutionOutcome
        if not isinstance(outcome, SQLConnectionAwareExecutionOutcome):
            raise SQLExecutionTraceContractError(
                "Input must be an instance of SQLConnectionAwareExecutionOutcome"
            )

        req = outcome.request
        sql_hash = hashlib.sha256(req.sql.encode("utf-8")).hexdigest()
        outcome_status = outcome.status.value if hasattr(outcome.status, "value") else str(outcome.status)
        plan_status = "planned" if outcome.plan else "no_plan"

        sanitized_error = None
        if outcome.error:
            from app.evaluation.failure_analytics import SQLFailureAnalyzer
            error_to_redact = outcome.error
            if req.connection_ref:
                error_to_redact = error_to_redact.replace(req.connection_ref, "[REDACTED_CONNECTION]")
            sanitized_error = SQLFailureAnalyzer._redact_secrets(error_to_redact, req.fixture_ref)

        return cls(
            version=SQL_EXECUTION_TRACE_VERSION,
            case_id=req.case_id,
            dialect=req.dialect.value if hasattr(req.dialect, "value") else str(req.dialect),
            execution_mode=req.config.execution_mode.value if hasattr(req.config.execution_mode, "value") else str(req.config.execution_mode),
            has_fixture_ref=req.fixture_ref is not None and bool(req.fixture_ref.strip()),
            has_connection_ref=req.connection_ref is not None and bool(req.connection_ref.strip()),
            sql_sha256=sql_hash,
            plan_status=plan_status,
            outcome_status=outcome_status,
            warnings=outcome.warnings,
            failure_category=failure_category,
            duration_ms=duration_ms,
            error=sanitized_error,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Returns a deterministic serialized dictionary representation."""
        return {
            "case_id": self.case_id,
            "dialect": self.dialect,
            "duration_ms": self.duration_ms,
            "error": self.error,
            "execution_mode": self.execution_mode,
            "failure_category": self.failure_category,
            "has_connection_ref": self.has_connection_ref,
            "has_fixture_ref": self.has_fixture_ref,
            "outcome_status": self.outcome_status,
            "plan_status": self.plan_status,
            "sql_sha256": self.sql_sha256,
            "version": self.version,
            "warnings": list(self.warnings),
        }
