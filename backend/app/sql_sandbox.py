import os
import sqlite3
from pathlib import Path
from typing import List, Dict, Any

from app.sql_safety import SqlSafetyValidator

class QueryTimeoutError(RuntimeError):
    """Raised when query execution exceeds the configured timeout limit."""
    pass

class RowLimitExceededError(RuntimeError):
    """Raised when query execution returns more rows than the configured maximum limit."""
    pass

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
        """
        # 1. Pre-Execution Safety Validation
        self.validator.ensure_read_only(sql)

        # 2. Setup Isolated Read-Only SQLite URI
        abs_path = os.path.abspath(self.db_path)
        if not os.path.exists(abs_path):
            raise ValueError(f"Target database does not exist: {abs_path}")

        # Format Path to strict file:// URI with mode=ro query parameter
        db_uri = Path(abs_path).as_uri() + "?mode=ro"

        # 3. Connection and Execution with Timeout Enforcement
        import time
        start_time = time.monotonic()

        def check_timeout():
            if time.monotonic() - start_time > self.timeout_seconds:
                return 1
            return 0

        conn = None
        try:
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
            
            return [dict(row) for row in rows]
        except sqlite3.OperationalError as e:
            # Detect if progress handler triggered the timeout abort
            if time.monotonic() - start_time > self.timeout_seconds:
                raise QueryTimeoutError("Query execution exceeded timeout")
            # Map sqlite3 engine level write violations and errors to standard high-level exception
            raise ValueError(f"Database execution error: {str(e)}")
        except QueryTimeoutError:
            # Reraise QueryTimeoutError directly
            raise
        except RowLimitExceededError:
            # Reraise RowLimitExceededError directly
            raise
        except Exception as e:
            raise ValueError(f"Sandbox execution failed: {str(e)}")
        finally:
            if conn:
                conn.close()
