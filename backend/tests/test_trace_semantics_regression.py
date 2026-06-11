import pytest
from unittest.mock import patch, MagicMock
from app.sql_pipeline import SQLGenerationPipeline
from app.trace.models import NL2SQLTrace

class RecordingTraceStore:
    def __init__(self):
        self.saved = []
    def save(self, trace: NL2SQLTrace):
        self.saved.append(trace)

@pytest.fixture
def mock_schema_manager():
    return MagicMock()

@pytest.fixture
def mock_nvidia_client():
    return MagicMock()

def test_success_trace_contract(mock_schema_manager, mock_nvidia_client):
    store = RecordingTraceStore()
    pipeline = SQLGenerationPipeline(schema_manager=mock_schema_manager, nvidia_client=mock_nvidia_client, trace_store=store)
    mock_nvidia_client.generate_sql.return_value = "SELECT * FROM test"

    with patch.object(pipeline.schema_pruner, 'prune_schema', return_value={"tables": {"test": {"columns": [{"name": "id", "type": "int", "primary_key": True}]}}, "estimated_tokens": 100}):
        with patch('app.sql_pipeline.SQLValidator.validate', return_value=(True, None)):
            pipeline.run_pipeline(job_id="j1", natural_query="q")

    trace = store.saved[0]
    assert trace.generated_sql == "SELECT\n  *\nFROM test"
    assert trace.last_generated_sql == trace.generated_sql
    assert trace.sql_valid is True
    assert trace.sql_validation_errors == []
    assert trace.error_type is None
    assert len(trace.attempts) == 1

def test_successful_retry_clears_top_level_validation_errors(mock_schema_manager, mock_nvidia_client):
    store = RecordingTraceStore()
    pipeline = SQLGenerationPipeline(schema_manager=mock_schema_manager, nvidia_client=mock_nvidia_client, trace_store=store)
    
    mock_nvidia_client.generate_sql.side_effect = ["SELECT broken", "SELECT * FROM test"]
    
    with patch.object(pipeline.schema_pruner, 'prune_schema', return_value={"tables": {"test": {"columns": [{"name": "id", "type": "int", "primary_key": True}]}}}):
        with patch('app.sql_pipeline.SQLValidator.validate', side_effect=[(False, "err"), (True, None)]):
            pipeline.run_pipeline(job_id="j1", natural_query="q", max_attempts=2)

    trace = store.saved[0]
    assert trace.generated_sql == "SELECT\n  *\nFROM test"
    assert trace.last_generated_sql == trace.generated_sql
    assert trace.sql_valid is True
    assert trace.sql_validation_errors == []
    assert trace.error_type is None
    assert len(trace.attempts) == 2
    assert trace.attempts[0]["valid"] is False
    assert trace.attempts[1]["valid"] is True

def test_final_failure_uses_last_attempt_validation_errors(mock_schema_manager, mock_nvidia_client):
    store = RecordingTraceStore()
    pipeline = SQLGenerationPipeline(schema_manager=mock_schema_manager, nvidia_client=mock_nvidia_client, trace_store=store)
    
    mock_nvidia_client.generate_sql.side_effect = ["SELECT broken", "DELETE FROM users;"]
    
    with patch.object(pipeline.schema_pruner, 'prune_schema', return_value={"tables": {"users": {"columns": [{"name": "id", "type": "int", "primary_key": True}]}}}):
        with patch('app.sql_pipeline.SQLValidator.validate', side_effect=[(False, "semantic err")]):
            pipeline.run_pipeline(job_id="j1", natural_query="q", max_attempts=2)

    trace = store.saved[0]
    assert trace.generated_sql is None
    assert trace.last_generated_sql == "DELETE FROM users;"
    assert trace.sql_valid is False
    assert trace.error_type == "sql_generation_failed"
    assert len(trace.sql_validation_errors) > 0
    assert trace.sql_validation_errors[0]["stage"] == "sql_guardrail"
    assert trace.sql_validation_errors[0]["type"] == "non_select_statement"
    assert len(trace.attempts) == 2

def test_guardrail_failure_fail_fast_trace_contract(mock_schema_manager, mock_nvidia_client):
    store = RecordingTraceStore()
    pipeline = SQLGenerationPipeline(schema_manager=mock_schema_manager, nvidia_client=mock_nvidia_client, trace_store=store)
    
    mock_nvidia_client.generate_sql.side_effect = ["DELETE FROM users;", "SELECT * FROM users;"]
    
    with patch.object(pipeline.schema_pruner, 'prune_schema', return_value={"tables": {"users": {"columns": [{"name": "id", "type": "int", "primary_key": True}]}}}):
        with patch('app.sql_pipeline.SQLValidator.validate', return_value=(True, None)):
            pipeline.run_pipeline(job_id="j1", natural_query="q", max_attempts=2)

    trace = store.saved[0]
    assert trace.generated_sql is None
    assert trace.last_generated_sql == "DELETE FROM users;"
    assert trace.sql_valid is False
    assert trace.error_type == "sql_generation_failed"
    assert len(trace.attempts) == 1
    assert trace.attempts[0]["valid"] is False
    assert trace.attempts[0]["validation_errors"][0]["stage"] == "sql_guardrail"

def test_all_guardrail_failures_fail_fast_trace_contract(mock_schema_manager, mock_nvidia_client):
    store = RecordingTraceStore()
    pipeline = SQLGenerationPipeline(schema_manager=mock_schema_manager, nvidia_client=mock_nvidia_client, trace_store=store)
    
    mock_nvidia_client.generate_sql.side_effect = ["DROP TABLE users;", "DELETE FROM users;"]
    
    with patch.object(pipeline.schema_pruner, 'prune_schema', return_value={"tables": {"users": {"columns": [{"name": "id", "type": "int", "primary_key": True}]}}}):
        with patch('app.sql_pipeline.SQLValidator.validate', return_value=(True, None)):
            pipeline.run_pipeline(job_id="j1", natural_query="q", max_attempts=2)

    trace = store.saved[0]
    assert trace.generated_sql is None
    assert trace.last_generated_sql == "DROP TABLE users;"
    assert trace.sql_valid is False
    assert trace.error_type == "sql_generation_failed"
    assert len(trace.sql_validation_errors) > 0
    assert trace.sql_validation_errors[0]["stage"] == "sql_guardrail"
    assert len(trace.attempts) == 1

def test_llm_api_failure_attempt_has_validation_errors(mock_schema_manager, mock_nvidia_client):
    store = RecordingTraceStore()
    pipeline = SQLGenerationPipeline(schema_manager=mock_schema_manager, nvidia_client=mock_nvidia_client, trace_store=store)
    
    mock_nvidia_client.generate_sql.side_effect = Exception("LLM API Down")
    
    with patch.object(pipeline.schema_pruner, 'prune_schema', return_value={"tables": {"users": {"columns": [{"name": "id", "type": "int", "primary_key": True}]}}}):
        pipeline.run_pipeline(job_id="j1", natural_query="q", max_attempts=1)

    trace = store.saved[0]
    assert trace.generated_sql is None
    assert trace.last_generated_sql is None
    assert trace.sql_valid is False
    assert trace.error_type == "sql_generation_failed"
    assert trace.sql_validation_errors[0]["type"] == "llm_api_error"
    assert trace.sql_validation_errors[0]["stage"] == "llm_generation"
    assert len(trace.attempts) == 1
    assert trace.attempts[0]["valid"] is False
    assert trace.attempts[0]["validation_errors"][0]["type"] == "llm_api_error"

def test_schema_pruning_error(mock_schema_manager, mock_nvidia_client):
    store = RecordingTraceStore()
    pipeline = SQLGenerationPipeline(schema_manager=mock_schema_manager, nvidia_client=mock_nvidia_client, trace_store=store)
    
    with patch.object(pipeline.schema_pruner, 'prune_schema', return_value={"error": "Schema err"}):
        pipeline.run_pipeline(job_id="j1", natural_query="q")

    trace = store.saved[0]
    assert trace.generated_sql is None
    assert trace.last_generated_sql is None
    assert trace.sql_valid is None
    assert trace.error_type == "schema_pruning_error"
    assert trace.error_message == "Schema err"

def test_input_error(mock_schema_manager, mock_nvidia_client):
    store = RecordingTraceStore()
    pipeline = SQLGenerationPipeline(schema_manager=mock_schema_manager, nvidia_client=mock_nvidia_client, trace_store=store)
    
    pipeline.run_pipeline(job_id="j1", natural_query="")
    
    trace = store.saved[0]
    assert trace.generated_sql is None
    assert trace.last_generated_sql is None
    assert trace.sql_valid is None
    assert trace.error_type == "input_error"
    assert "boş olamaz" in trace.error_message.lower()

def test_schema_pruning_exception_trace_contract(mock_schema_manager, mock_nvidia_client):
    store = RecordingTraceStore()
    pipeline = SQLGenerationPipeline(
        schema_manager=mock_schema_manager,
        nvidia_client=mock_nvidia_client,
        trace_store=store,
    )

    with patch.object(
        pipeline.schema_pruner,
        "prune_schema",
        side_effect=Exception("graph exploded"),
    ):
        result = pipeline.run_pipeline(job_id="j1", natural_query="q")

    trace = store.saved[0]

    assert result["success"] is False
    assert trace.generated_sql is None
    assert trace.last_generated_sql is None
    assert trace.sql_valid is None
    assert trace.sql_validation_errors == []
    assert trace.attempts == []
    assert trace.error_type == "schema_pruning_exception"
    assert "graph exploded" in trace.error_message

def test_excel_parse_error_trace_contract(mock_schema_manager, mock_nvidia_client):
    store = RecordingTraceStore()
    pipeline = SQLGenerationPipeline(
        schema_manager=mock_schema_manager,
        nvidia_client=mock_nvidia_client,
        trace_store=store,
    )

    with patch(
        "app.sql_pipeline.parse_excel_request",
        side_effect=Exception("bad excel"),
    ):
        result = pipeline.run_pipeline(
            job_id="j1",
            excel_file_path="/tmp/fake.xlsx",
            natural_query=None,
        )

    trace = store.saved[0]

    assert result["success"] is False
    assert trace.generated_sql is None
    assert trace.last_generated_sql is None
    assert trace.sql_valid is None
    assert trace.sql_validation_errors == []
    assert trace.attempts == []
    assert trace.error_type == "excel_parse_error"
    assert "bad excel" in trace.error_message

def test_semantic_missing_column_taxonomy_contract(mock_schema_manager, mock_nvidia_client):
    store = RecordingTraceStore()
    pipeline = SQLGenerationPipeline(
        schema_manager=mock_schema_manager,
        nvidia_client=mock_nvidia_client,
        trace_store=store,
    )

    mock_nvidia_client.generate_sql.return_value = "SELECT missing_col FROM users"

    with patch.object(pipeline.schema_pruner, 'prune_schema', return_value={"tables": {"users": {"columns": [{"name": "id", "type": "int", "primary_key": True}]}}}):
        with patch('app.sql_pipeline.SQLValidator.validate', return_value=(False, "Missing column: missing_col")):
            pipeline.run_pipeline(job_id="j1", natural_query="q", max_attempts=1)

    trace = store.saved[0]
    assert trace.error_type == "sql_generation_failed"
    assert len(trace.attempts) == 1
    assert trace.attempts[0]["validation_errors"][0]["stage"] == "semantic_validation"
    assert trace.attempts[0]["validation_errors"][0]["type"] == "missing_column"
    assert trace.sql_validation_errors[0]["stage"] == "semantic_validation"
    assert trace.sql_validation_errors[0]["type"] == "missing_column"

def test_ast_parse_error_taxonomy_contract(mock_schema_manager, mock_nvidia_client):
    store = RecordingTraceStore()
    pipeline = SQLGenerationPipeline(
        schema_manager=mock_schema_manager,
        nvidia_client=mock_nvidia_client,
        trace_store=store,
    )

    mock_nvidia_client.generate_sql.return_value = "SELECT * FROM users WHERE ;"

    with patch.object(pipeline.schema_pruner, 'prune_schema', return_value={"tables": {"users": {"columns": [{"name": "id", "type": "int", "primary_key": True}]}}}):
        with patch('app.sql_guardrail.SQLGuardrailValidator.validate', return_value=[]):
            pipeline.run_pipeline(job_id="j1", natural_query="q", max_attempts=1)

    trace = store.saved[0]
    assert trace.error_type == "sql_generation_failed"
    assert len(trace.attempts) == 1
    assert trace.attempts[0]["validation_errors"][0]["stage"] == "ast_parse"
    assert trace.attempts[0]["validation_errors"][0]["type"] == "syntax_error"
    assert trace.sql_validation_errors[0]["stage"] == "ast_parse"
    assert trace.sql_validation_errors[0]["type"] == "syntax_error"
