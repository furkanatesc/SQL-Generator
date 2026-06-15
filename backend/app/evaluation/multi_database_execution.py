from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Tuple, Mapping, Optional
import hashlib
import time
import os

from app.sql_sandbox import ReadOnlySqlSandbox
from app.sql_safety import SqlSafetyValidator

SQL_MULTI_DATABASE_EXECUTION_VERSION = "sql_multi_database_execution_v1"


class SQLMultiDatabaseExecutionContractError(ValueError):
    """Raised when multi-database execution contract rules or configurations are violated."""
    pass


class SQLDatabaseDialect(str, Enum):
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"
    ORACLE = "oracle"


class SQLExecutionMode(str, Enum):
    READ_ONLY = "read_only"
    EXPLAIN_ONLY = "explain_only"


class SQLExecutionAdapterCapability(str, Enum):
    LOCAL_FIXTURE = "local_fixture"
    CONNECTION_REF = "connection_ref"
    READ_ONLY = "read_only"
    EXPLAIN_ONLY = "explain_only"


def _validate_rate(val: Any, name: str):
    if not isinstance(val, (int, float)) or isinstance(val, bool):
        raise SQLMultiDatabaseExecutionContractError(f"{name} must be a number")
    if val <= 0:
        raise SQLMultiDatabaseExecutionContractError(f"{name} must be greater than 0")


@dataclass(frozen=True)
class SQLDatabaseExecutionConfig:
    dialect: SQLDatabaseDialect
    timeout_seconds: float = 2.0
    max_rows: int = 1000
    execution_mode: SQLExecutionMode = SQLExecutionMode.READ_ONLY

    def __post_init__(self):
        if not isinstance(self.dialect, SQLDatabaseDialect):
            try:
                object.__setattr__(self, "dialect", SQLDatabaseDialect(self.dialect))
            except ValueError:
                raise SQLMultiDatabaseExecutionContractError(f"Invalid dialect: {self.dialect}")

        _validate_rate(self.timeout_seconds, "timeout_seconds")

        if not isinstance(self.max_rows, int) or isinstance(self.max_rows, bool):
            raise SQLMultiDatabaseExecutionContractError("max_rows must be an integer")
        if self.max_rows <= 0:
            raise SQLMultiDatabaseExecutionContractError("max_rows must be greater than 0")

        if not isinstance(self.execution_mode, SQLExecutionMode):
            try:
                object.__setattr__(self, "execution_mode", SQLExecutionMode(self.execution_mode))
            except ValueError:
                raise SQLMultiDatabaseExecutionContractError(f"Invalid execution mode: {self.execution_mode}")


@dataclass(frozen=True)
class SQLDatabaseExecutionRequest:
    case_id: str
    sql: str
    dialect: SQLDatabaseDialect
    fixture_ref: Optional[str]
    connection_ref: Optional[str]
    config: SQLDatabaseExecutionConfig

    def __post_init__(self):
        if not self.case_id or not isinstance(self.case_id, str) or not self.case_id.strip():
            raise SQLMultiDatabaseExecutionContractError("case_id cannot be empty")
        if not self.sql or not isinstance(self.sql, str) or not self.sql.strip():
            raise SQLMultiDatabaseExecutionContractError("sql cannot be empty")

        if not isinstance(self.dialect, SQLDatabaseDialect):
            try:
                object.__setattr__(self, "dialect", SQLDatabaseDialect(self.dialect))
            except ValueError:
                raise SQLMultiDatabaseExecutionContractError(f"Invalid dialect: {self.dialect}")

        if not isinstance(self.config, SQLDatabaseExecutionConfig):
            raise SQLMultiDatabaseExecutionContractError("config must be a SQLDatabaseExecutionConfig")

        if self.dialect != self.config.dialect:
            raise SQLMultiDatabaseExecutionContractError("dialect must match config.dialect")

        if self.fixture_ref is not None and not isinstance(self.fixture_ref, str):
            raise SQLMultiDatabaseExecutionContractError("fixture_ref must be a string or None")
        if self.connection_ref is not None and not isinstance(self.connection_ref, str):
            raise SQLMultiDatabaseExecutionContractError("connection_ref must be a string or None")

        has_fixture = self.fixture_ref is not None and bool(self.fixture_ref.strip())
        has_connection = self.connection_ref is not None and bool(self.connection_ref.strip())

        if has_fixture and has_connection:
            raise SQLMultiDatabaseExecutionContractError("Cannot specify both fixture_ref and connection_ref")
        if not has_fixture and not has_connection:
            raise SQLMultiDatabaseExecutionContractError("Must specify either fixture_ref or connection_ref")


@dataclass(frozen=True)
class SQLDatabaseExecutionResult:
    version: str
    case_id: str
    dialect: SQLDatabaseDialect
    sql: str
    sql_sha256: str
    rows: Tuple[Mapping[str, Any], ...]
    row_count: int
    truncated: bool
    execution_error: Optional[str]
    duration_ms: float
    warnings: Tuple[str, ...]

    def __post_init__(self):
        if self.version != "sql_multi_database_execution_v1":
            raise SQLMultiDatabaseExecutionContractError(f"Invalid version: {self.version}")
        if not self.case_id or not isinstance(self.case_id, str) or not self.case_id.strip():
            raise SQLMultiDatabaseExecutionContractError("case_id cannot be empty")
        if not self.sql or not isinstance(self.sql, str) or not self.sql.strip():
            raise SQLMultiDatabaseExecutionContractError("sql cannot be empty")

        if not isinstance(self.dialect, SQLDatabaseDialect):
            try:
                object.__setattr__(self, "dialect", SQLDatabaseDialect(self.dialect))
            except ValueError:
                raise SQLMultiDatabaseExecutionContractError(f"Invalid dialect: {self.dialect}")

        if not self.sql_sha256 or not isinstance(self.sql_sha256, str) or not self.sql_sha256.strip():
            raise SQLMultiDatabaseExecutionContractError("sql_sha256 cannot be empty")

        if not isinstance(self.row_count, int) or isinstance(self.row_count, bool) or self.row_count < 0:
            raise SQLMultiDatabaseExecutionContractError("row_count must be a non-negative integer")

        if not isinstance(self.truncated, bool):
            raise SQLMultiDatabaseExecutionContractError("truncated must be a boolean")

        if self.execution_error is not None and not isinstance(self.execution_error, str):
            raise SQLMultiDatabaseExecutionContractError("execution_error must be a string or None")

        if not isinstance(self.duration_ms, (int, float)) or isinstance(self.duration_ms, bool) or self.duration_ms < 0:
            raise SQLMultiDatabaseExecutionContractError("duration_ms must be a non-negative number")

        if not isinstance(self.rows, tuple):
            try:
                object.__setattr__(self, "rows", tuple(self.rows))
            except TypeError:
                raise SQLMultiDatabaseExecutionContractError("rows must be a tuple")
        for r in self.rows:
            if not isinstance(r, dict):
                raise SQLMultiDatabaseExecutionContractError("Each row must be a dictionary/mapping")

        if not isinstance(self.warnings, tuple):
            try:
                object.__setattr__(self, "warnings", tuple(self.warnings))
            except TypeError:
                raise SQLMultiDatabaseExecutionContractError("warnings must be a tuple")
        for w in self.warnings:
            if not isinstance(w, str):
                raise SQLMultiDatabaseExecutionContractError("All warnings must be strings")


class SQLDatabaseExecutionAdapter(ABC):
    @property
    @abstractmethod
    def dialect(self) -> SQLDatabaseDialect:
        pass

    @abstractmethod
    def execute(self, request: SQLDatabaseExecutionRequest) -> SQLDatabaseExecutionResult:
        pass

    @abstractmethod
    def capabilities(self) -> Tuple[SQLExecutionAdapterCapability, ...]:
        pass


class SQLiteDatabaseExecutionAdapter(SQLDatabaseExecutionAdapter):
    def __init__(self, fixtures_dir: str):
        if not fixtures_dir or not isinstance(fixtures_dir, str) or not fixtures_dir.strip():
            raise SQLMultiDatabaseExecutionContractError("fixtures_dir cannot be empty")
        self.fixtures_dir = fixtures_dir

    @property
    def dialect(self) -> SQLDatabaseDialect:
        return SQLDatabaseDialect.SQLITE

    def capabilities(self) -> Tuple[SQLExecutionAdapterCapability, ...]:
        return (
            SQLExecutionAdapterCapability.LOCAL_FIXTURE,
            SQLExecutionAdapterCapability.READ_ONLY,
        )

    def _resolve_db_path(self, fixture_ref: str) -> str:
        if not fixture_ref or not fixture_ref.strip():
            raise SQLMultiDatabaseExecutionContractError("fixture_ref cannot be empty")

        if os.path.isabs(fixture_ref):
            raise SQLMultiDatabaseExecutionContractError("fixture_ref must be relative to fixtures_dir")

        fixtures_root = os.path.abspath(self.fixtures_dir)

        candidate_names = (f"{fixture_ref}.db", fixture_ref)
        for name in candidate_names:
            candidate = os.path.abspath(os.path.join(fixtures_root, name))
            if not candidate.startswith(fixtures_root + os.sep):
                raise SQLMultiDatabaseExecutionContractError("fixture_ref cannot escape fixtures_dir")
            if os.path.exists(candidate):
                return candidate

        raise SQLMultiDatabaseExecutionContractError(f"Fixture database not found: '{fixture_ref}'")

    def execute(self, request: SQLDatabaseExecutionRequest) -> SQLDatabaseExecutionResult:
        if not isinstance(request, SQLDatabaseExecutionRequest):
            raise SQLMultiDatabaseExecutionContractError("request must be a SQLDatabaseExecutionRequest")

        if request.dialect != SQLDatabaseDialect.SQLITE:
            raise SQLMultiDatabaseExecutionContractError("SQLite adapter only supports SQLite dialect requests")

        if request.connection_ref is not None:
            raise SQLMultiDatabaseExecutionContractError("SQLite adapter does not support connection_ref")

        # Resolving fixture path
        db_path = self._resolve_db_path(request.fixture_ref)

        # Unsafe SQL pre-check
        try:
            SqlSafetyValidator().ensure_read_only(request.sql)
        except ValueError as e:
            raise SQLMultiDatabaseExecutionContractError(f"Unsafe SQL query: {e}")

        # Initialize ReadOnlySqlSandbox
        sandbox = ReadOnlySqlSandbox(
            db_path=db_path,
            timeout_seconds=request.config.timeout_seconds,
            max_rows=request.config.max_rows
        )

        start_time = time.monotonic()
        sql_sha256 = hashlib.sha256(request.sql.encode("utf-8")).hexdigest()

        execution_error = None
        rows = ()
        row_count = 0
        truncated = False
        warnings = []

        try:
            rows_list = sandbox.execute(request.sql)
            rows = tuple(rows_list)
            row_count = len(rows)
        except Exception as e:
            execution_error = str(e)

        duration_ms = (time.monotonic() - start_time) * 1000.0

        return SQLDatabaseExecutionResult(
            version=SQL_MULTI_DATABASE_EXECUTION_VERSION,
            case_id=request.case_id,
            dialect=SQLDatabaseDialect.SQLITE,
            sql=request.sql,
            sql_sha256=sql_sha256,
            rows=rows,
            row_count=row_count,
            truncated=truncated,
            execution_error=execution_error,
            duration_ms=duration_ms,
            warnings=tuple(warnings)
        )


@dataclass(frozen=True)
class SQLDatabaseExecutionRouter:
    adapters: Tuple[SQLDatabaseExecutionAdapter, ...]

    def __post_init__(self):
        if not isinstance(self.adapters, tuple):
            try:
                object.__setattr__(self, "adapters", tuple(self.adapters))
            except TypeError:
                raise SQLMultiDatabaseExecutionContractError("adapters must be a tuple")

        dialects = []
        for adapter in self.adapters:
            if not isinstance(adapter, SQLDatabaseExecutionAdapter):
                raise SQLMultiDatabaseExecutionContractError(
                    "All adapters must be subclasses of SQLDatabaseExecutionAdapter"
                )
            dialects.append(adapter.dialect)

        if len(dialects) != len(set(dialects)):
            raise SQLMultiDatabaseExecutionContractError("Duplicate adapter dialects found")

    def get_adapter(self, dialect: SQLDatabaseDialect) -> SQLDatabaseExecutionAdapter:
        if not isinstance(dialect, SQLDatabaseDialect):
            try:
                dialect = SQLDatabaseDialect(dialect)
            except ValueError:
                raise SQLMultiDatabaseExecutionContractError(f"Invalid dialect: {dialect}")

        for adapter in self.adapters:
            if adapter.dialect == dialect:
                return adapter
        raise SQLMultiDatabaseExecutionContractError(f"Unsupported dialect: {dialect.value}")

    def execute(self, request: SQLDatabaseExecutionRequest) -> SQLDatabaseExecutionResult:
        if not isinstance(request, SQLDatabaseExecutionRequest):
            raise SQLMultiDatabaseExecutionContractError("request must be a SQLDatabaseExecutionRequest")

        adapter = self.get_adapter(request.dialect)
        return adapter.execute(request)
