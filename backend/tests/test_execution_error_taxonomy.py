import sqlite3
import pytest
from app.sql_sandbox import ReadOnlySqlSandbox
from app.sql_execution_errors import SqlExecutionError

@pytest.fixture
def temp_db(tmp_path):
    """
    Creates a temporary SQLite database with a 'users' table and initial records.
    """
    db_file = tmp_path / "taxonomy_test.db"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);")
    cursor.execute("INSERT INTO users (name) VALUES ('Alice');")
    cursor.execute("INSERT INTO users (name) VALUES ('Bob');")
    conn.commit()
    conn.close()
    return str(db_file)

def test_timeout_classification(temp_db):
    # Heavy recursive query to trigger timeout
    slow_query = """
    WITH RECURSIVE cnt(x) AS (
      SELECT 1
      UNION ALL
      SELECT x + 1 FROM cnt WHERE x < 100000000
    )
    SELECT sum(x) FROM cnt;
    """
    sandbox = ReadOnlySqlSandbox(temp_db, timeout_seconds=0.001)
    
    with pytest.raises(SqlExecutionError) as exc:
        sandbox.execute(slow_query)
    
    assert exc.value.code == "query_timeout"
    assert exc.value.stage == "sql_execution"

def test_row_limit_classification(temp_db):
    sandbox = ReadOnlySqlSandbox(temp_db, max_rows=1)
    
    with pytest.raises(SqlExecutionError) as exc:
        sandbox.execute("SELECT * FROM users ORDER BY id ASC;")
        
    assert exc.value.code == "row_limit_exceeded"
    assert exc.value.stage == "sql_execution"

def test_missing_table_classification(temp_db):
    sandbox = ReadOnlySqlSandbox(temp_db)
    
    with pytest.raises(SqlExecutionError) as exc:
        sandbox.execute("SELECT * FROM does_not_exist;")
        
    assert exc.value.code == "missing_table"
    assert exc.value.stage == "sql_execution"
    assert "no such table" in exc.value.message.lower()

def test_missing_column_classification(temp_db):
    sandbox = ReadOnlySqlSandbox(temp_db)
    
    with pytest.raises(SqlExecutionError) as exc:
        sandbox.execute("SELECT does_not_exist FROM users;")
        
    assert exc.value.code == "missing_column"
    assert exc.value.stage == "sql_execution"
    assert "no such column" in exc.value.message.lower()

def test_syntax_error_classification(temp_db):
    sandbox = ReadOnlySqlSandbox(temp_db)
    
    # Trigger parser parse error inside the sandbox execution path
    with pytest.raises(SqlExecutionError) as exc:
        sandbox.execute("SELECT FROM users WHERE;")
        
    assert exc.value.code == "syntax_error"
    assert exc.value.stage == "sql_execution"

def test_read_only_violation_driver_level(temp_db):
    sandbox = ReadOnlySqlSandbox(temp_db)
    
    # Bypass safety validator to prove driver-level mapping works
    sandbox.validator.ensure_read_only = lambda sql: None
    
    with pytest.raises(SqlExecutionError) as exc:
        sandbox.execute("DELETE FROM users WHERE id = 1;")
        
    assert exc.value.code == "read_only_violation"
    assert exc.value.stage == "sql_execution"
    assert "readonly database" in exc.value.message.lower()

def test_database_not_found_classification():
    sandbox = ReadOnlySqlSandbox("non_existent_directory_12345/missing.db")
    
    with pytest.raises(SqlExecutionError) as exc:
        sandbox.execute("SELECT * FROM users;")
        
    assert exc.value.code == "database_not_found"
    assert exc.value.stage == "sql_execution"
    assert "unable to open database" in exc.value.message.lower()
