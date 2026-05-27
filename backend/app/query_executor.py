from typing import List, Dict, Any
from app.sql_sandbox import ReadOnlySqlSandbox

class QueryExecutor:
    """
    Query Executor Service
    Provides high-level APIs to safely execute query operations in a sandboxed path.
    """

    @staticmethod
    def execute_sandboxed(sql: str, db_path: str) -> List[Dict[str, Any]]:
        """
        Executes the given SQL statement inside the read-only sandbox.
        """
        sandbox = ReadOnlySqlSandbox(db_path)
        return sandbox.execute(sql)
