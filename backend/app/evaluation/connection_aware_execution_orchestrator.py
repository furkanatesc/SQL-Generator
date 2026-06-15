from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Tuple, Optional
from app.evaluation.multi_database_execution import (
    SQLDatabaseExecutionRequest,
    SQLDatabaseExecutionResult,
    SQLDatabaseExecutionRouter,
)
from app.evaluation.connection_aware_execution import (
    SQLConnectionAwareExecutionPlan,
    SQLConnectionAwareExecutionPlanner,
)

SQL_CONNECTION_AWARE_EXECUTION_ORCHESTRATOR_VERSION = "sql_connection_aware_execution_orchestrator_v1"


class SQLConnectionAwareExecutionOrchestratorContractError(ValueError):
    """Raised when connection-aware execution orchestrator constraints are violated."""
    pass


class SQLConnectionAwareExecutionOutcomeStatus(str, Enum):
    EXECUTED = "executed"
    BLOCKED_LIVE_CONNECTION = "blocked_live_connection"
    REJECTED = "rejected"


@dataclass(frozen=True)
class SQLConnectionAwareExecutionOrchestratorConfig:
    allow_live_connection_execution: bool = False
    return_rejected_outcome: bool = True

    def __post_init__(self):
        if not isinstance(self.allow_live_connection_execution, bool):
            raise SQLConnectionAwareExecutionOrchestratorContractError(
                "allow_live_connection_execution must be a boolean"
            )
        if not isinstance(self.return_rejected_outcome, bool):
            raise SQLConnectionAwareExecutionOrchestratorContractError(
                "return_rejected_outcome must be a boolean"
            )

        if self.allow_live_connection_execution:
            raise SQLConnectionAwareExecutionOrchestratorContractError(
                "allow_live_connection_execution=True is not supported in this version (no live adapters available)"
            )


@dataclass(frozen=True)
class SQLConnectionAwareExecutionOutcome:
    version: str
    request: SQLDatabaseExecutionRequest
    plan: Optional[SQLConnectionAwareExecutionPlan]
    status: SQLConnectionAwareExecutionOutcomeStatus
    execution_result: Optional[SQLDatabaseExecutionResult]
    error: Optional[str]
    warnings: Tuple[str, ...]

    def __post_init__(self):
        if self.version != SQL_CONNECTION_AWARE_EXECUTION_ORCHESTRATOR_VERSION:
            raise SQLConnectionAwareExecutionOrchestratorContractError(
                f"Invalid outcome version: {self.version}"
            )

        if not isinstance(self.request, SQLDatabaseExecutionRequest):
            raise SQLConnectionAwareExecutionOrchestratorContractError(
                "request must be a SQLDatabaseExecutionRequest"
            )

        if not isinstance(self.status, SQLConnectionAwareExecutionOutcomeStatus):
            try:
                object.__setattr__(
                    self, "status", SQLConnectionAwareExecutionOutcomeStatus(self.status)
                )
            except ValueError:
                raise SQLConnectionAwareExecutionOrchestratorContractError(
                    f"Invalid status: {self.status}"
                )

        if self.plan is not None and not isinstance(self.plan, SQLConnectionAwareExecutionPlan):
            raise SQLConnectionAwareExecutionOrchestratorContractError(
                "plan must be a SQLConnectionAwareExecutionPlan or None"
            )

        if self.execution_result is not None and not isinstance(
            self.execution_result, SQLDatabaseExecutionResult
        ):
            raise SQLConnectionAwareExecutionOrchestratorContractError(
                "execution_result must be a SQLDatabaseExecutionResult or None"
            )

        if not isinstance(self.warnings, tuple):
            raise SQLConnectionAwareExecutionOrchestratorContractError(
                "warnings must be a tuple"
            )
        for w in self.warnings:
            if not isinstance(w, str):
                raise SQLConnectionAwareExecutionOrchestratorContractError(
                    "All warnings must be strings"
                )

        # Invariant checks based on status
        if self.status == SQLConnectionAwareExecutionOutcomeStatus.EXECUTED:
            if self.plan is None:
                raise SQLConnectionAwareExecutionOrchestratorContractError(
                    "plan is required for EXECUTED outcome"
                )
            if self.execution_result is None:
                raise SQLConnectionAwareExecutionOrchestratorContractError(
                    "execution_result is required for EXECUTED outcome"
                )
            if self.error is not None:
                raise SQLConnectionAwareExecutionOrchestratorContractError(
                    "error must be None for EXECUTED outcome"
                )

        elif self.status == SQLConnectionAwareExecutionOutcomeStatus.BLOCKED_LIVE_CONNECTION:
            if self.plan is None:
                raise SQLConnectionAwareExecutionOrchestratorContractError(
                    "plan is required for BLOCKED_LIVE_CONNECTION outcome"
                )
            if self.execution_result is not None:
                raise SQLConnectionAwareExecutionOrchestratorContractError(
                    "execution_result must be None for BLOCKED_LIVE_CONNECTION outcome"
                )
            if not self.error or not isinstance(self.error, str) or not self.error.strip():
                raise SQLConnectionAwareExecutionOrchestratorContractError(
                    "error description is required for BLOCKED_LIVE_CONNECTION outcome"
                )
            if not self.plan.requires_live_connection:
                raise SQLConnectionAwareExecutionOrchestratorContractError(
                    "plan requires_live_connection must be True for BLOCKED_LIVE_CONNECTION outcome"
                )

        elif self.status == SQLConnectionAwareExecutionOutcomeStatus.REJECTED:
            if self.execution_result is not None:
                raise SQLConnectionAwareExecutionOrchestratorContractError(
                    "execution_result must be None for REJECTED outcome"
                )
            if not self.error or not isinstance(self.error, str) or not self.error.strip():
                raise SQLConnectionAwareExecutionOrchestratorContractError(
                    "error description is required for REJECTED outcome"
                )


@dataclass(frozen=True)
class SQLConnectionAwareExecutionOrchestrator:
    planner: SQLConnectionAwareExecutionPlanner
    router: SQLDatabaseExecutionRouter
    config: SQLConnectionAwareExecutionOrchestratorConfig = field(
        default_factory=SQLConnectionAwareExecutionOrchestratorConfig
    )

    def __post_init__(self):
        if not isinstance(self.planner, SQLConnectionAwareExecutionPlanner):
            raise SQLConnectionAwareExecutionOrchestratorContractError(
                "planner must be a SQLConnectionAwareExecutionPlanner instance"
            )
        if not isinstance(self.router, SQLDatabaseExecutionRouter):
            raise SQLConnectionAwareExecutionOrchestratorContractError(
                "router must be a SQLDatabaseExecutionRouter instance"
            )
        if not isinstance(self.config, SQLConnectionAwareExecutionOrchestratorConfig):
            raise SQLConnectionAwareExecutionOrchestratorContractError(
                "config must be a SQLConnectionAwareExecutionOrchestratorConfig instance"
            )

    def execute(self, request: SQLDatabaseExecutionRequest) -> SQLConnectionAwareExecutionOutcome:
        plan = None
        try:
            if not isinstance(request, SQLDatabaseExecutionRequest):
                raise SQLConnectionAwareExecutionOrchestratorContractError(
                    "request must be a SQLDatabaseExecutionRequest"
                )

            # 1. Plan
            plan = self.planner.plan(request)

            # 2. Block live connection requests
            if plan.requires_live_connection:
                return SQLConnectionAwareExecutionOutcome(
                    version=SQL_CONNECTION_AWARE_EXECUTION_ORCHESTRATOR_VERSION,
                    request=request,
                    plan=plan,
                    status=SQLConnectionAwareExecutionOutcomeStatus.BLOCKED_LIVE_CONNECTION,
                    execution_result=None,
                    error="Live connection execution is blocked in this version (no live adapters available)",
                    warnings=()
                )

            # 3. Check local execution dialect support
            if not plan.can_execute_locally:
                raise SQLConnectionAwareExecutionOrchestratorContractError(
                    f"Local execution is not supported for dialect: {plan.effective_dialect.value}"
                )

            # 4. Route and execute
            execution_result = self.router.execute(request)

            return SQLConnectionAwareExecutionOutcome(
                version=SQL_CONNECTION_AWARE_EXECUTION_ORCHESTRATOR_VERSION,
                request=request,
                plan=plan,
                status=SQLConnectionAwareExecutionOutcomeStatus.EXECUTED,
                execution_result=execution_result,
                error=None,
                warnings=()
            )

        except Exception as e:
            if self.config.return_rejected_outcome:
                return SQLConnectionAwareExecutionOutcome(
                    version=SQL_CONNECTION_AWARE_EXECUTION_ORCHESTRATOR_VERSION,
                    request=request,
                    plan=plan if isinstance(plan, SQLConnectionAwareExecutionPlan) else None,
                    status=SQLConnectionAwareExecutionOutcomeStatus.REJECTED,
                    execution_result=None,
                    error=str(e),
                    warnings=()
                )
            else:
                raise
