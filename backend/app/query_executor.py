from typing import List, Dict, Any
from app.sql_sandbox import ReadOnlySqlSandbox

class QueryExecutor:
    """
    Query Executor Service
    Provides high-level APIs to safely execute query operations in a sandboxed path.
    """

    @staticmethod
    def execute_sandboxed(
        sql: str,
        db_path: str,
        timeout_seconds: float = 2.0,
        max_rows: int = 1000,
    ) -> List[Dict[str, Any]]:
        """
        Executes the given SQL statement inside the read-only sandbox.
        """
        sandbox = ReadOnlySqlSandbox(
            db_path,
            timeout_seconds=timeout_seconds,
            max_rows=max_rows,
        )
        return sandbox.execute(sql)
