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

    with patch.object(pipeline.schema_pruner, 'prune_schema', return_value={"tables": {"test": {}}, "estimated_tokens": 100}):
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
    
    with patch.object(pipeline.schema_pruner, 'prune_schema', return_value={"tables": {"test": {}}}):
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
    
    with patch.object(pipeline.schema_pruner, 'prune_schema', return_value={"tables": {"users": {}}}):
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

def test_guardrail_retry_success_trace_contract(mock_schema_manager, mock_nvidia_client):
    store = RecordingTraceStore()
    pipeline = SQLGenerationPipeline(schema_manager=mock_schema_manager, nvidia_client=mock_nvidia_client, trace_store=store)
    
    mock_nvidia_client.generate_sql.side_effect = ["DELETE FROM users;", "SELECT * FROM users;"]
    
    with patch.object(pipeline.schema_pruner, 'prune_schema', return_value={"tables": {"users": {}}}):
        with patch('app.sql_pipeline.SQLValidator.validate', return_value=(True, None)):
            pipeline.run_pipeline(job_id="j1", natural_query="q", max_attempts=2)

    trace = store.saved[0]
    assert trace.generated_sql == "SELECT\n  *\nFROM users"
    assert trace.last_generated_sql == trace.generated_sql
    assert trace.sql_valid is True
    assert trace.sql_validation_errors == []
    assert trace.error_type is None
    assert len(trace.attempts) == 2
    assert trace.attempts[0]["valid"] is False
    assert trace.attempts[0]["validation_errors"][0]["stage"] == "sql_guardrail"
    assert trace.attempts[1]["valid"] is True

def test_all_guardrail_failures_trace_contract(mock_schema_manager, mock_nvidia_client):
    store = RecordingTraceStore()
    pipeline = SQLGenerationPipeline(schema_manager=mock_schema_manager, nvidia_client=mock_nvidia_client, trace_store=store)
    
    mock_nvidia_client.generate_sql.side_effect = ["DROP TABLE users;", "DELETE FROM users;"]
    
    with patch.object(pipeline.schema_pruner, 'prune_schema', return_value={"tables": {"users": {}}}):
        with patch('app.sql_pipeline.SQLValidator.validate', return_value=(True, None)):
            pipeline.run_pipeline(job_id="j1", natural_query="q", max_attempts=2)

    trace = store.saved[0]
    assert trace.generated_sql is None
    assert trace.last_generated_sql == "DELETE FROM users;"
    assert trace.sql_valid is False
    assert trace.error_type == "sql_generation_failed"
    assert len(trace.sql_validation_errors) > 0
    assert trace.sql_validation_errors[0]["stage"] == "sql_guardrail"
    assert len(trace.attempts) == 2

def test_llm_api_failure_attempt_has_validation_errors(mock_schema_manager, mock_nvidia_client):
    store = RecordingTraceStore()
    pipeline = SQLGenerationPipeline(schema_manager=mock_schema_manager, nvidia_client=mock_nvidia_client, trace_store=store)
    
    mock_nvidia_client.generate_sql.side_effect = Exception("LLM API Down")
    
    with patch.object(pipeline.schema_pruner, 'prune_schema', return_value={"tables": {"users": {}}}):
        pipeline.run_pipeline(job_id="j1", natural_query="q", max_attempts=1)

    trace = store.saved[0]
    assert trace.generated_sql is None
    assert trace.last_generated_sql is None
    assert trace.sql_valid is False
    assert trace.error_type == "sql_generation_failed"
    assert trace.sql_validation_errors[0]["type"] == "llm_api_error"
    assert "üretimi" in trace.error_message.lower() or "uret" in trace.error_message.lower()
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
    assert "boş olamaz" in trace.error_message.lower() or "bo" in trace.error_message.lower()
