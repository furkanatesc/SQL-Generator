import sqlite3
import pytest
from app.sql_sandbox import ReadOnlySqlSandbox, QueryTimeoutError

@pytest.fixture
def temp_db(tmp_path):
    """
    Creates a temporary SQLite database with a 'users' table and initial records.
    """
    db_file = tmp_path / "sandbox_timeout_test.db"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);")
    cursor.execute("INSERT INTO users (name) VALUES ('Alice');")
    cursor.execute("INSERT INTO users (name) VALUES ('Bob');")
    conn.commit()
    conn.close()
    return str(db_file)

def test_fast_query_succeeds_within_timeout(temp_db):
    # Safe SELECT statement within the default timeout (2.0s) should pass
    sandbox = ReadOnlySqlSandbox(temp_db, timeout_seconds=2.0)
    results = sandbox.execute("SELECT * FROM users ORDER BY id ASC;")
    assert len(results) == 2
    assert results[0]["name"] == "Alice"

def test_slow_query_interrupted_by_timeout(temp_db):
    # A heavy SQLite recursive query designed to run long
    slow_query = """
    WITH RECURSIVE cnt(x) AS (
      SELECT 1
      UNION ALL
      SELECT x + 1 FROM cnt WHERE x < 100000000
    )
    SELECT sum(x) FROM cnt;
    """
    # Setting an extremely low timeout (e.g. 1ms) to force a timeout
    sandbox = ReadOnlySqlSandbox(temp_db, timeout_seconds=0.001)
    
    with pytest.raises(QueryTimeoutError, match="Query execution exceeded timeout"):
        sandbox.execute(slow_query)

def test_connection_cleanup_after_timeout(temp_db):
    """
    Verifies that even after a query times out, the database connection is closed cleanly,
    and subsequent fast queries execute successfully on the same database without locks.
    """
    slow_query = """
    WITH RECURSIVE cnt(x) AS (
      SELECT 1
      UNION ALL
      SELECT x + 1 FROM cnt WHERE x < 100000000
    )
    SELECT sum(x) FROM cnt;
    """
    sandbox = ReadOnlySqlSandbox(temp_db, timeout_seconds=0.001)
    
    # Trigger timeout interruption
    with pytest.raises(QueryTimeoutError):
        sandbox.execute(slow_query)
        
    # Verify we can execute a fresh query on the same database using a clean sandbox instance
    fresh_sandbox = ReadOnlySqlSandbox(temp_db, timeout_seconds=2.0)
    result = fresh_sandbox.execute("SELECT COUNT(*) AS count FROM users;")
    
    assert len(result) == 1
    assert result[0]["count"] == 2

def test_timeout_config_changes_behavior(temp_db):
    """
    Checks that altering the timeout behaves correctly (low timeout fails, high timeout succeeds).
    """
    medium_query = """
    WITH RECURSIVE cnt(x) AS (
      SELECT 1
      UNION ALL
      SELECT x + 1 FROM cnt WHERE x < 200000
    )
    SELECT sum(x) FROM cnt;
    """
    
    # 1. Very low timeout should fail
    sandbox_low = ReadOnlySqlSandbox(temp_db, timeout_seconds=0.000001)
    with pytest.raises(QueryTimeoutError):
        sandbox_low.execute(medium_query)
        
    # 2. Reasonable timeout should pass
    sandbox_high = ReadOnlySqlSandbox(temp_db, timeout_seconds=5.0)
    result = sandbox_high.execute(medium_query)
    assert len(result) == 1
    assert result[0]["sum(x)"] > 0

def test_write_blocking_still_enforced(temp_db):
    """
    Ensures that timeout enhancements did not degrade PR 12.1's read-only/write-blocking security boundaries.
    """
    sandbox = ReadOnlySqlSandbox(temp_db, timeout_seconds=2.0)
    
    # Rejects DML
    with pytest.raises(ValueError):
        sandbox.execute("DELETE FROM users WHERE id = 1;")
    with pytest.raises(ValueError):
        sandbox.execute("INSERT INTO users (name) VALUES ('Charlie');")
    with pytest.raises(ValueError):
        sandbox.execute("UPDATE users SET name = 'Dave' WHERE id = 1;")
        
    # Rejects DDL
    with pytest.raises(ValueError):
        sandbox.execute("DROP TABLE users;")
        
    # Verify DB state unchanged
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users;")
    count = cursor.fetchone()[0]
    conn.close()
    assert count == 2
