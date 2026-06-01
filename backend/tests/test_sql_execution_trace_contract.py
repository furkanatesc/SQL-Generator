import sqlite3
import pytest
from unittest.mock import MagicMock, patch

from app.sql_execution_errors import SqlExecutionError
from app.sql_sandbox import ReadOnlySqlSandbox
from app.sql_pipeline import SQLGenerationPipeline


@pytest.fixture
def temp_db(tmp_path):
    """
    Creates a temporary SQLite database with a 'users' table and initial records.
    """
    db_file = tmp_path / "sandbox_trace_test.db"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT);")
    cursor.execute("INSERT INTO users (name) VALUES ('Alice');")
    conn.commit()
    conn.close()
    return str(db_file)


# A. SqlExecutionError Code Preservation
def test_sql_execution_error_retains_code_and_stage():
    err = SqlExecutionError(
        code="custom_code_123",
        message="Test custom message",
        stage="sql_execution",
        details={"extra": "data"}
    )
    assert err.code == "custom_code_123"
    assert err.stage == "sql_execution"
    assert err.details == {"extra": "data"}
    assert str(err) == "Test custom message"


# B. Sandbox Taxonomy Classification Tests
def test_sandbox_query_timeout_preserves_taxonomy(temp_db):
    # Heavy recursive query to trigger timeout in sandbox
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


def test_sandbox_row_limit_preserves_taxonomy(temp_db):
    sandbox = ReadOnlySqlSandbox(temp_db, max_rows=1)
    
    # Selecting multiple rows when limit is 1
    sandbox.execute("SELECT * FROM users;") # 1 row in DB - succeeds
    
    # insert another row to trigger limit
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (name) VALUES ('Bob');")
    conn.commit()
    conn.close()
    
    with pytest.raises(SqlExecutionError) as exc:
        sandbox.execute("SELECT * FROM users;")
        
    assert exc.value.code == "row_limit_exceeded"
    assert exc.value.stage == "sql_execution"


def test_sandbox_missing_table_preserves_taxonomy(temp_db):
    sandbox = ReadOnlySqlSandbox(temp_db)
    
    with pytest.raises(SqlExecutionError) as exc:
        sandbox.execute("SELECT * FROM non_existent_table;")
        
    assert exc.value.code == "missing_table"
    assert exc.value.stage == "sql_execution"


def test_sandbox_missing_column_preserves_taxonomy(temp_db):
    sandbox = ReadOnlySqlSandbox(temp_db)
    
    with pytest.raises(SqlExecutionError) as exc:
        sandbox.execute("SELECT non_existent_column FROM users;")
        
    assert exc.value.code == "missing_column"
    assert exc.value.stage == "sql_execution"


# C. Public Response vs Debug Trace Segregation Contracts (Safety regression)
@patch("app.sql_pipeline.PromptTemplateManager.get_writer_prompt", return_value="dummy prompt")
@patch("app.sql_pipeline.SQLGuardrailValidator.validate", return_value=[])
def test_unsafe_sql_not_exposed_in_public_response_but_stage_is_traceable(mock_guardrail, mock_prompt):
    mock_llm_provider = MagicMock()
    mock_response = MagicMock()
    # Unsafe writing query that will bypass guardrail but trigger sandbox safety
    mock_response.sql = "DELETE FROM users WHERE id = 1;"
    mock_llm_provider.generate_sql.return_value = mock_response

    trace_store = MagicMock(); del trace_store.save_legacy
    pipeline = SQLGenerationPipeline(
        trace_store=trace_store,
        llm_provider=mock_llm_provider,
    )

    with patch("app.sql_pipeline.SchemaPruner.prune_schema") as mock_prune:
        mock_prune.return_value = {
            "tables": {
                "users": {
                    "columns": [{"name": "id"}]
                }
            }
        }
        
        result = pipeline.run_pipeline(
            job_id="test_safety_job",
            natural_query="delete user 1",
            max_attempts=1
        )

    # Public response generated_sql MUST be completely empty for unsafe SQL
    assert result["success"] is False
    assert result["generated_sql"] == ""
    assert "attempts" in result
    assert len(result["attempts"]) == 1
    
    # Public attempts validation error check
    last_attempt = result["attempts"][-1]
    assert last_attempt["valid"] is False
    assert len(last_attempt["validation_errors"]) == 1
    assert last_attempt["validation_errors"][0]["stage"] == "sql_sandbox_safety"
    assert last_attempt["validation_errors"][0]["type"] == "unsafe_sql"

    # Verify debug trace gets the detailed last_generated_sql but public response does not leak it
    trace_store.save.assert_called_once()
    trace = trace_store.save.call_args[0][0]
    
    # Inside internal trace we can keep the blocked sql and error stage for analytics
    assert getattr(trace, "generated_sql") is None
    assert getattr(trace, "last_generated_sql") == "DELETE FROM users WHERE id = 1;"
    assert getattr(trace, "sql_validation_errors")[0]["stage"] == "sql_sandbox_safety"
    assert getattr(trace, "sql_validation_errors")[0]["type"] == "unsafe_sql"


@patch("app.sql_pipeline.PromptTemplateManager.get_writer_prompt", return_value="dummy prompt")
def test_no_raw_exception_stack_trace_leakage_in_public_response(mock_prompt):
    mock_llm_provider = MagicMock()
    mock_llm_provider.generate_sql.side_effect = Exception("Critical internal server database socket crashed!")

    trace_store = MagicMock(); del trace_store.save_legacy
    pipeline = SQLGenerationPipeline(
        trace_store=trace_store,
        llm_provider=mock_llm_provider,
    )

    with patch("app.sql_pipeline.SchemaPruner.prune_schema") as mock_prune:
        mock_prune.return_value = {"tables": {}}
        result = pipeline.run_pipeline(
            job_id="test_exception_job",
            natural_query="get all users",
            max_attempts=1
        )

    # Public response validation error should have clean messages, not raw backend exception stack traces
    assert result["success"] is False
    assert "error" in result
    assert "crashed!" not in result["error"]
    assert "SQL üretimi başarısız oldu" in result["error"]

