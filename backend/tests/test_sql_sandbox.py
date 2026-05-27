import sqlite3
import pytest
from app.sql_sandbox import ReadOnlySqlSandbox

@pytest.fixture
def temp_db(tmp_path):
    """
    Creates a temporary SQLite database with a 'users' table and initial records.
    """
    db_file = tmp_path / "sandbox_test.db"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);")
    cursor.execute("INSERT INTO users (name) VALUES ('Alice');")
    cursor.execute("INSERT INTO users (name) VALUES ('Bob');")
    conn.commit()
    conn.close()
    return str(db_file)

def test_sandbox_happy_path(temp_db):
    # Safe SELECT statement execution
    sandbox = ReadOnlySqlSandbox(temp_db)
    results = sandbox.execute("SELECT * FROM users ORDER BY id ASC;")
    
    assert len(results) == 2
    assert results[0]["id"] == 1
    assert results[0]["name"] == "Alice"
    assert results[1]["id"] == 2
    assert results[1]["name"] == "Bob"

def test_sandbox_write_blocked_and_state_unchanged(temp_db):
    sandbox = ReadOnlySqlSandbox(temp_db)
    
    # Helper to count records
    def get_users_count():
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users;")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    
    # Get initial state
    before_count = get_users_count()
    assert before_count == 2
    
    # Blocked write attempt: DELETE
    with pytest.raises(ValueError):
        sandbox.execute("DELETE FROM users WHERE id = 1;")
        
    # Blocked write attempt: INSERT
    with pytest.raises(ValueError):
        sandbox.execute("INSERT INTO users (name) VALUES ('Charlie');")
        
    # Blocked write attempt: UPDATE
    with pytest.raises(ValueError):
        sandbox.execute("UPDATE users SET name = 'Dave' WHERE id = 1;")

    # Blocked write attempt: DROP TABLE
    with pytest.raises(ValueError):
        sandbox.execute("DROP TABLE users;")
        
    # Confirm DB state remains completely unchanged after blocked write attempts
    after_count = get_users_count()
    assert after_count == before_count

def test_database_driver_level_readonly_isolation(temp_db):
    """
    Verifies that the SQLite connection itself enforces read-only behavior.
    We bypass/override the pre-execution safety validator to show that even if
    a write query makes it to the database connection, it is strictly blocked by the SQLite driver.
    """
    sandbox = ReadOnlySqlSandbox(temp_db)
    
    # Override validator to allow everything
    sandbox.validator.ensure_read_only = lambda sql: None
    
    # Try to execute a write statement. It should pass validation but fail at the DB engine/driver level.
    with pytest.raises(ValueError, match="Database execution error: attempt to write a readonly database"):
        sandbox.execute("DELETE FROM users WHERE id = 1;")
        
    # Confirm record count remains 2
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users;")
    count = cursor.fetchone()[0]
    conn.close()
    assert count == 2
