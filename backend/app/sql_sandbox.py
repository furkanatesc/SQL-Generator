import os
import sqlite3
import time
from pathlib import Path
from typing import List, Dict, Any

from app.sql_safety import SqlSafetyValidator
from app.sql_execution_errors import (
    SqlExecutionError,
    QueryTimeoutError,
    RowLimitExceededError,
    classify_execution_error,
)
from app.result_shape_validator import ResultShapeValidator

class ReadOnlySqlSandbox:
    """
    Read-Only Isolation SQL Sandbox
    
    Current implementation is specialized for SQLite target databases.
    Enforces absolute read-only behavior at the SQLite driver layer via URI mode=ro parameters.
    Designed with a simple execute boundary to support future database adapter strategies (e.g., PostgreSQL/Oracle).
    """

    def __init__(self, db_path: str, timeout_seconds: float = 2.0, max_rows: int = 1000):
        """
        Initializes the SQLite Read-Only Isolation Sandbox with the target DB file path, timeout, and max row limit.
        """
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than 0")
        if max_rows <= 0:
            raise ValueError("max_rows must be greater than 0")

        self.db_path = db_path
        self.timeout_seconds = timeout_seconds
        self.max_rows = max_rows
        self.validator = SqlSafetyValidator()

    def execute(self, sql: str) -> List[Dict[str, Any]]:
        """
        Validates the SQL statement for read-only SELECT safety, connects to the
        target SQLite database in strict read-only mode, executes it, and returns the results.
        Enforces configurable query timeout limit and maximum row limit.
        Uses ResultShapeValidator to ensure correct response format.
        Categorizes and converts all execution errors through classify_execution_error.
        """
        start_time = time.monotonic()
        conn = None
        try:
            # 1. Pre-Execution Safety Validation
            self.validator.ensure_read_only(sql)

            # 2. Setup Isolated Read-Only SQLite URI
            abs_path = os.path.abspath(self.db_path)
            if not os.path.exists(abs_path):
                # Raise SQLite-like OperationalError to trigger correct classification
                raise sqlite3.OperationalError(f"unable to open database file: {abs_path}")

            # Format Path to strict file:// URI with mode=ro query parameter
            db_uri = Path(abs_path).as_uri() + "?mode=ro"

            def check_timeout():
                if time.monotonic() - start_time > self.timeout_seconds:
                    return 1
                return 0

            # 3. Connection and Execution with Timeout/Limit Enforcement
            conn = sqlite3.connect(db_uri, uri=True)
            conn.row_factory = sqlite3.Row
            
            # Register progress handler to interrupt queries exceeding timeout limit
            conn.set_progress_handler(check_timeout, 1000)
            
            cursor = conn.cursor()
            cursor.execute(sql)
            
            # Fetch up to max_rows + 1 to detect limit violation
            rows = cursor.fetchmany(self.max_rows + 1)
            if len(rows) > self.max_rows:
                raise RowLimitExceededError(f"Query returned more than {self.max_rows} rows")
            
            # Convert SQLite rows to list[dict]
            result = [dict(row) for row in rows]
            
            # 4. Result Shape Validation (prior to returning result)
            ResultShapeValidator.validate(result)
            
            return result

        except Exception as e:
            # Detect if progress handler triggered the timeout abort
            is_timeout = (time.monotonic() - start_time > self.timeout_seconds)
            if is_timeout:
                raise classify_execution_error(QueryTimeoutError("Query execution exceeded timeout"))
            
            raise classify_execution_error(e)
            
        finally:
            if conn:
                conn.close()
