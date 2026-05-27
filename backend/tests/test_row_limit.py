import sqlite3
import pytest
from app.sql_sandbox import ReadOnlySqlSandbox, RowLimitExceededError, QueryTimeoutError
from app.sql_execution_errors import SqlExecutionError
from app.query_executor import QueryExecutor

@pytest.fixture
def temp_db(tmp_path):
    """
    Creates a temporary SQLite database with a 'users' table containing exactly 3 records.
    """
    db_file = tmp_path / "sandbox_row_limit_test.db"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);")
    cursor.execute("INSERT INTO users (name) VALUES ('Alice');")
    cursor.execute("INSERT INTO users (name) VALUES ('Bob');")
    cursor.execute("INSERT INTO users (name) VALUES ('Charlie');")
    conn.commit()
    conn.close()
    return str(db_file)

def test_query_under_row_limit_succeeds(temp_db):
    # Query returning fewer rows than max_rows must pass cleanly
    sandbox = ReadOnlySqlSandbox(temp_db, max_rows=10)
    result = sandbox.execute("SELECT * FROM users ORDER BY id ASC;")
    assert len(result) == 3
    assert result[0]["name"] == "Alice"
    assert result[1]["name"] == "Bob"
    assert result[2]["name"] == "Charlie"

def test_query_exceeding_row_limit_fails(temp_db):
    # Query returning more than max_rows must raise RowLimitExceededError
    sandbox = ReadOnlySqlSandbox(temp_db, max_rows=2)
    
    with pytest.raises(RowLimitExceededError, match="Query returned more than 2 rows"):
        sandbox.execute("SELECT * FROM users ORDER BY id ASC;")

def test_query_exactly_at_row_limit_boundary_succeeds(temp_db):
    # Query returning exactly max_rows must succeed cleanly
    sandbox = ReadOnlySqlSandbox(temp_db, max_rows=3)
    result = sandbox.execute("SELECT * FROM users ORDER BY id ASC;")
    assert len(result) == 3

def test_query_executor_passes_max_rows_parameter(temp_db):
    # Integration check proving QueryExecutor forwards max_rows successfully
    with pytest.raises(RowLimitExceededError):
        QueryExecutor.execute_sandboxed(
            sql="SELECT * FROM users ORDER BY id ASC;",
            db_path=temp_db,
            max_rows=2
        )

def test_invalid_parameters_rejected(temp_db):
    # Constructor must validate max_rows and timeout_seconds are positive
    with pytest.raises(ValueError, match="max_rows must be greater than 0"):
        ReadOnlySqlSandbox(temp_db, max_rows=0)
        
    with pytest.raises(ValueError, match="max_rows must be greater than 0"):
        ReadOnlySqlSandbox(temp_db, max_rows=-5)

    with pytest.raises(ValueError, match="timeout_seconds must be greater than 0"):
        ReadOnlySqlSandbox(temp_db, timeout_seconds=0)

    with pytest.raises(ValueError, match="timeout_seconds must be greater than 0"):
        ReadOnlySqlSandbox(temp_db, timeout_seconds=-0.5)

def test_timeout_behavior_not_masked_by_row_limit(temp_db):
    # A heavy slow recursive query should still trigger timeout instead of row limit
    slow_query = """
    WITH RECURSIVE cnt(x) AS (
      SELECT 1
      UNION ALL
      SELECT x + 1 FROM cnt WHERE x < 100000000
    )
    SELECT sum(x) FROM cnt;
    """
    sandbox = ReadOnlySqlSandbox(temp_db, timeout_seconds=0.001, max_rows=1000)
    
    with pytest.raises(QueryTimeoutError):
        sandbox.execute(slow_query)

def test_write_blocking_still_fully_enforced(temp_db):
    # PR 12.1 write blocking security constraints must remain completely functional
    sandbox = ReadOnlySqlSandbox(temp_db, max_rows=10)
    
    with pytest.raises(SqlExecutionError):
        sandbox.execute("DELETE FROM users WHERE id = 1;")
    with pytest.raises(SqlExecutionError):
        sandbox.execute("INSERT INTO users (name) VALUES ('Dave');")
        
    # Assert DB state is untouched
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users;")
    count = cursor.fetchone()[0]
    conn.close()
    assert count == 3
