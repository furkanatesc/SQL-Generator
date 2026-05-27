import sqlite3
import pytest
from app.sql_sandbox import ReadOnlySqlSandbox
from app.result_shape_validator import validate_result_shape
from app.sql_execution_errors import SqlExecutionError

@pytest.fixture
def temp_db(tmp_path):
    """
    Creates a temporary SQLite database with a 'users' table and initial records.
    """
    db_file = tmp_path / "shape_test.db"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);")
    cursor.execute("INSERT INTO users (name) VALUES ('Alice');")
    cursor.execute("INSERT INTO users (name) VALUES ('Bob');")
    conn.commit()
    conn.close()
    return str(db_file)

def test_result_shape_validator_direct_cases():
    # Pass path
    validate_result_shape([{"id": 1}])
    validate_result_shape([])
    validate_result_shape([{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}])

    # Non-list result throws SqlExecutionError
    with pytest.raises(SqlExecutionError) as exc:
        validate_result_shape(None)
    assert exc.value.code == "invalid_result_shape"

    with pytest.raises(SqlExecutionError) as exc:
        validate_result_shape({"id": 1})
    assert exc.value.code == "invalid_result_shape"

    # Non-dict row throws SqlExecutionError
    with pytest.raises(SqlExecutionError) as exc:
        validate_result_shape([("id", 1)])
    assert exc.value.code == "invalid_result_shape"

    with pytest.raises(SqlExecutionError) as exc:
        validate_result_shape([["id", 1]])
    assert exc.value.code == "invalid_result_shape"

    # Mixed row type throws SqlExecutionError
    with pytest.raises(SqlExecutionError) as exc:
        validate_result_shape([{"id": 1}, ["bad"]])
    assert exc.value.code == "invalid_result_shape"

    # Non-string key throws SqlExecutionError
    with pytest.raises(SqlExecutionError) as exc:
        validate_result_shape([{1: "bad"}])
    assert exc.value.code == "invalid_result_shape"

def test_happy_path_sandbox_result_shape(temp_db):
    sandbox = ReadOnlySqlSandbox(temp_db)
    result = sandbox.execute("SELECT id, name FROM users ORDER BY id ASC;")
    
    assert isinstance(result, list)
    assert len(result) == 2
    assert isinstance(result[0], dict)
    assert isinstance(result[1], dict)
    assert set(result[0].keys()) == {"id", "name"}
    assert result[0]["id"] == 1
    assert result[0]["name"] == "Alice"
