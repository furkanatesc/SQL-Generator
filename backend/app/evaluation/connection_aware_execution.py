from dataclasses import dataclass, field
from typing import Any, Tuple, Optional
from app.evaluation.multi_database_execution import (
    SQLDatabaseDialect,
    SQLDatabaseExecutionRequest,
    SQLExecutionMode,
)
from app.evaluation.connection_abstraction import (
    SQLResolvedConnection,
    SQLConnectionResolver,
    SQLConnectionAccessMode,
)

SQL_CONNECTION_AWARE_EXECUTION_VERSION = "sql_connection_aware_execution_v1"


class SQLConnectionAwareExecutionContractError(ValueError):
    """Raised when connection-aware execution planning or configuration constraints are violated."""
    pass


@dataclass(frozen=True)
class SQLConnectionAwareExecutionConfig:
    allow_live_connection_plans: bool = False

    def __post_init__(self):
        if not isinstance(self.allow_live_connection_plans, bool):
            raise SQLConnectionAwareExecutionContractError("allow_live_connection_plans must be a boolean")


@dataclass(frozen=True)
class SQLConnectionAwareExecutionPlan:
    version: str
    request: SQLDatabaseExecutionRequest
    resolved_connection: Optional[SQLResolvedConnection]
    effective_dialect: SQLDatabaseDialect
    effective_max_rows: int
    effective_timeout_seconds: float
    uses_fixture: bool
    uses_connection: bool
    can_execute_locally: bool
    requires_live_connection: bool
    warnings: Tuple[str, ...]

    def __post_init__(self):
        if self.version != SQL_CONNECTION_AWARE_EXECUTION_VERSION:
            raise SQLConnectionAwareExecutionContractError(f"Invalid plan version: {self.version}")

        if not isinstance(self.request, SQLDatabaseExecutionRequest):
            raise SQLConnectionAwareExecutionContractError("request must be a SQLDatabaseExecutionRequest")

        if self.resolved_connection is not None and not isinstance(self.resolved_connection, SQLResolvedConnection):
            raise SQLConnectionAwareExecutionContractError(
                "resolved_connection must be a SQLResolvedConnection or None"
            )

        if not isinstance(self.effective_dialect, SQLDatabaseDialect):
            raise SQLConnectionAwareExecutionContractError("effective_dialect must be a SQLDatabaseDialect")

        if not isinstance(self.effective_max_rows, int) or isinstance(self.effective_max_rows, bool) or self.effective_max_rows <= 0:
            raise SQLConnectionAwareExecutionContractError("effective_max_rows must be a positive integer")

        if not isinstance(self.effective_timeout_seconds, (int, float)) or isinstance(self.effective_timeout_seconds, bool) or self.effective_timeout_seconds <= 0:
            raise SQLConnectionAwareExecutionContractError("effective_timeout_seconds must be a positive number")

        if not isinstance(self.uses_fixture, bool):
            raise SQLConnectionAwareExecutionContractError("uses_fixture must be a boolean")

        if not isinstance(self.uses_connection, bool):
            raise SQLConnectionAwareExecutionContractError("uses_connection must be a boolean")

        if not isinstance(self.can_execute_locally, bool):
            raise SQLConnectionAwareExecutionContractError("can_execute_locally must be a boolean")

        if not isinstance(self.requires_live_connection, bool):
            raise SQLConnectionAwareExecutionContractError("requires_live_connection must be a boolean")

        if not isinstance(self.warnings, tuple):
            raise SQLConnectionAwareExecutionContractError("warnings must be a tuple")

        for w in self.warnings:
            if not isinstance(w, str):
                raise SQLConnectionAwareExecutionContractError("All warnings must be strings")

        # Semantic Invariants Validation
        if self.uses_fixture == self.uses_connection:
            raise SQLConnectionAwareExecutionContractError(
                "exactly one of uses_fixture or uses_connection must be true"
            )

        if self.uses_fixture:
            if self.resolved_connection is not None:
                raise SQLConnectionAwareExecutionContractError(
                    "fixture-backed plans cannot include resolved_connection"
                )
            if self.requires_live_connection:
                raise SQLConnectionAwareExecutionContractError(
                    "fixture-backed plans cannot require live connection"
                )

        if self.uses_connection:
            if self.resolved_connection is None:
                raise SQLConnectionAwareExecutionContractError(
                    "connection-backed plans require resolved_connection"
                )
            if self.can_execute_locally:
                raise SQLConnectionAwareExecutionContractError(
                    "connection-backed plans cannot execute locally"
                )
            if not self.requires_live_connection:
                raise SQLConnectionAwareExecutionContractError(
                    "connection-backed plans must require live connection"
                )

        if self.effective_dialect != self.request.dialect:
            raise SQLConnectionAwareExecutionContractError(
                "effective_dialect must match request.dialect"
            )


@dataclass(frozen=True)
class SQLConnectionAwareExecutionPlanner:
    resolver: Optional[SQLConnectionResolver] = None
    config: SQLConnectionAwareExecutionConfig = field(
        default_factory=SQLConnectionAwareExecutionConfig
    )

    def __post_init__(self):
        if self.resolver is not None and not isinstance(self.resolver, SQLConnectionResolver):
            raise SQLConnectionAwareExecutionContractError("resolver must be a SQLConnectionResolver instance or None")
        if not isinstance(self.config, SQLConnectionAwareExecutionConfig):
            raise SQLConnectionAwareExecutionContractError("config must be a SQLConnectionAwareExecutionConfig instance")

    def plan(self, request: SQLDatabaseExecutionRequest) -> SQLConnectionAwareExecutionPlan:
        if not isinstance(request, SQLDatabaseExecutionRequest):
            raise SQLConnectionAwareExecutionContractError("request must be a SQLDatabaseExecutionRequest")

        if request.config.execution_mode != SQLExecutionMode.READ_ONLY:
            raise SQLConnectionAwareExecutionContractError(
                "connection-aware execution planning currently supports only read_only execution mode"
            )

        uses_fixture = request.fixture_ref is not None
        uses_connection = request.connection_ref is not None

        if uses_fixture:
            resolved_connection = None
            effective_dialect = request.dialect
            effective_max_rows = request.config.max_rows
            effective_timeout_seconds = request.config.timeout_seconds
            can_execute_locally = (request.dialect == SQLDatabaseDialect.SQLITE)
            requires_live_connection = False
        else:  # uses_connection
            if not self.config.allow_live_connection_plans:
                raise SQLConnectionAwareExecutionContractError(
                    "connection_ref planning is disabled by default"
                )
            if self.resolver is None:
                raise SQLConnectionAwareExecutionContractError(
                    "resolver is required when planning connection_ref requests"
                )

            resolved = self.resolver.resolve(request.connection_ref)

            if resolved.dialect != request.dialect:
                raise SQLConnectionAwareExecutionContractError(
                    "request dialect does not match resolved connection dialect"
                )

            if resolved.access_mode != SQLConnectionAccessMode.READ_ONLY:
                raise SQLConnectionAwareExecutionContractError(
                    "resolved connection is not read_only"
                )

            resolved_connection = resolved
            effective_dialect = resolved.dialect
            effective_max_rows = min(request.config.max_rows, resolved.max_rows)
            effective_timeout_seconds = min(request.config.timeout_seconds, resolved.timeout_seconds)
            can_execute_locally = False
            requires_live_connection = True

        return SQLConnectionAwareExecutionPlan(
            version=SQL_CONNECTION_AWARE_EXECUTION_VERSION,
            request=request,
            resolved_connection=resolved_connection,
            effective_dialect=effective_dialect,
            effective_max_rows=effective_max_rows,
            effective_timeout_seconds=effective_timeout_seconds,
            uses_fixture=uses_fixture,
            uses_connection=uses_connection,
            can_execute_locally=can_execute_locally,
            requires_live_connection=requires_live_connection,
            warnings=()
        )
