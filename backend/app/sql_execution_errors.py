import sqlite3
import sqlglot.errors

class SqlExecutionError(RuntimeError):
    """
    Base class for structured SQL execution errors.
    """
    def __init__(
        self,
        code: str,
        message: str,
        stage: str = "sql_execution",
        details: dict | None = None,
    ):
        super().__init__(message)
        self.code = code
        self.message = message
        self.stage = stage
        self.details = details or {}

class QueryTimeoutError(SqlExecutionError):
    """Raised when query execution exceeds the configured timeout limit."""
    def __init__(self, message: str = "Query execution exceeded timeout", details: dict | None = None):
        super().__init__(
            code="query_timeout",
            message=message,
            stage="sql_execution",
            details=details,
        )

class RowLimitExceededError(SqlExecutionError):
    """Raised when query execution returns more rows than the configured maximum limit."""
    def __init__(self, message: str, details: dict | None = None):
        super().__init__(
            code="row_limit_exceeded",
            message=message,
            stage="sql_execution",
            details=details,
        )

def classify_execution_error(exc: Exception) -> SqlExecutionError:
    """
    Maps any driver, validation, timeout, limit, or generic exception
    to a structured, production-grade SqlExecutionError instance.
    """
    # 1. If it's already an instance of SqlExecutionError, propagate directly
    if isinstance(exc, SqlExecutionError):
        return exc

    details = {
        "raw_error": str(exc),
        "error_type": type(exc).__name__,
    }

    # 2. SQLite OperationalError mappings
    if isinstance(exc, sqlite3.OperationalError):
        msg = str(exc).lower()
        if "no such table" in msg:
            return SqlExecutionError(
                code="missing_table",
                message=str(exc),
                stage="sql_execution",
                details=details,
            )
        elif "no such column" in msg or "has no column" in msg:
            return SqlExecutionError(
                code="missing_column",
                message=str(exc),
                stage="sql_execution",
                details=details,
            )
        elif "syntax error" in msg:
            return SqlExecutionError(
                code="syntax_error",
                message=str(exc),
                stage="sql_execution",
                details=details,
            )
        elif "readonly database" in msg or "read-only database" in msg:
            return SqlExecutionError(
                code="read_only_violation",
                message=str(exc),
                stage="sql_execution",
                details=details,
            )
        elif "permission denied" in msg:
            return SqlExecutionError(
                code="permission_denied",
                message=str(exc),
                stage="sql_execution",
                details=details,
            )
        elif "unable to open database" in msg:
            return SqlExecutionError(
                code="database_not_found",
                message=str(exc),
                stage="sql_execution",
                details=details,
            )
        else:
            return SqlExecutionError(
                code="execution_error",
                message=str(exc),
                stage="sql_execution",
                details=details,
            )

    # 3. Sqlglot Parsing Failure mappings
    if isinstance(exc, (sqlglot.errors.ParseError, sqlglot.errors.SqlglotError)):
        return SqlExecutionError(
            code="syntax_error",
            message=str(exc),
            stage="sql_execution",
            details=details,
        )

    # 4. ValueError mappings (used for pre-execution safety validation checks)
    if isinstance(exc, ValueError):
        msg = str(exc).lower()
        if "write operation" in msg or "write keyword" in msg or "only read-only" in msg:
            return SqlExecutionError(
                code="read_only_violation",
                message=str(exc),
                stage="sql_execution",
                details=details,
            )
        elif "empty" in msg or "no valid statement" in msg or "single statement" in msg:
            return SqlExecutionError(
                code="syntax_error",
                message=str(exc),
                stage="sql_execution",
                details=details,
            )
        elif "does not exist" in msg and "database" in msg:
            return SqlExecutionError(
                code="database_not_found",
                message=str(exc),
                stage="sql_execution",
                details=details,
            )
        else:
            return SqlExecutionError(
                code="execution_error",
                message=str(exc),
                stage="sql_execution",
                details=details,
            )

    # 5. Generic Exception Fallback
    return SqlExecutionError(
        code="execution_error",
        message=str(exc),
        stage="sql_execution",
        details=details,
    )
