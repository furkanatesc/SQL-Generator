import pytest
from unittest.mock import patch, MagicMock

from app.sql_pipeline import SQLGenerationPipeline
from app.trace.models import NL2SQLTrace


class RecordingTraceStore:
    def __init__(self):
        self.saved = []

    def save(self, trace: NL2SQLTrace):
        self.saved.append(trace)

class FailingTraceStore:
    def save(self, trace: NL2SQLTrace):
        raise RuntimeError("trace db down")

@pytest.fixture
def mock_schema_manager():
    sm = MagicMock()
    return sm

@pytest.fixture
def mock_nvidia_client():
    client = MagicMock()
    client.generate_sql.return_value = "SELECT * FROM test"
    return client

def test_pipeline_trace_capture_success(mock_schema_manager, mock_nvidia_client):
    store = RecordingTraceStore()
    pipeline = SQLGenerationPipeline(
        schema_manager=mock_schema_manager,
        nvidia_client=mock_nvidia_client,
        trace_store=store
    )
    
    # Mock prune_schema to bypass actual pruning logic
    with patch.object(pipeline.schema_pruner, 'prune_schema') as mock_prune:
        mock_prune.return_value = {
            "tables": {"test": {"columns": [{"name": "id", "type": "int", "primary_key": True}]}},
            "estimated_tokens": 100,
            "debug_trace": {
                "selected_tables": ["test"]
            }
        }
        
        # also mock validator to always pass
        with patch('app.sql_pipeline.SQLValidator.validate', return_value=(True, None)):
            res = pipeline.run_pipeline(
                job_id="job123",
                natural_query="get test",
                dialect="postgres"
            )
            
    assert res["success"] is True
    assert len(store.saved) == 1
    
    trace = store.saved[0]
    assert trace.raw_query == "get test"
    assert trace.selected_tables == ["test"]
    
    assert trace.schema_context_selection is not None
    assert trace.schema_context_selection["selector_version"] == "deterministic_v1"
    assert "test" in trace.schema_context_selection["selected_tables"]
    
    assert trace.generated_sql == "SELECT\n  *\nFROM test"
    assert trace.metadata["job_id"] == "job123"
    assert trace.metadata["dialect"] == "postgres"
    assert "total" in trace.latency_ms
    assert trace.sql_valid is True
    assert trace.last_generated_sql == trace.generated_sql
    assert len(trace.attempts) == 1
    assert trace.sql_validation_errors == []
    
    # Assert prune_schema was called correctly (without token_budget kwargs)
    mock_prune.assert_called_once()
    _, kwargs = mock_prune.call_args
    assert "token_budget" not in kwargs
    assert "policy" in kwargs
    assert kwargs["policy"].token_budget == 8000

def test_pipeline_trace_store_none(mock_schema_manager, mock_nvidia_client):
    pipeline = SQLGenerationPipeline(
        schema_manager=mock_schema_manager,
        nvidia_client=mock_nvidia_client,
        trace_store=None
    )
    
    with patch.object(pipeline.schema_pruner, 'prune_schema') as mock_prune:
        mock_prune.return_value = {
            "tables": {"test": {"columns": [{"name": "id", "type": "int", "primary_key": True}]}},
            "estimated_tokens": 100
        }
        
        with patch('app.sql_pipeline.SQLValidator.validate', return_value=(True, None)):
            res = pipeline.run_pipeline(
                job_id="job123",
                natural_query="get test"
            )
            
    assert res["success"] is True
    # If no error is raised, behavior is preserved. 
    # trace_store=None correctly skipped capture.

def test_pipeline_trace_capture_failure(mock_schema_manager, mock_nvidia_client):
    store = RecordingTraceStore()
    pipeline = SQLGenerationPipeline(
        schema_manager=mock_schema_manager,
        nvidia_client=mock_nvidia_client,
        trace_store=store
    )
    
    with patch.object(pipeline.schema_pruner, 'prune_schema') as mock_prune:
        mock_prune.return_value = {
            "error": "Failed to prune"
        }
        
        res = pipeline.run_pipeline(
            job_id="job123",
            natural_query="get test"
        )
            
    assert res["success"] is False
    assert res["error"] == "Failed to prune"
    
    assert len(store.saved) == 1
    trace = store.saved[0]
    assert trace.error_message == "Failed to prune"
    assert trace.error_type == "schema_pruning_failed"
    assert trace.generated_sql is None

def test_pipeline_trace_save_error_does_not_break_flow(mock_schema_manager, mock_nvidia_client):
    store = FailingTraceStore()
    pipeline = SQLGenerationPipeline(
        schema_manager=mock_schema_manager,
        nvidia_client=mock_nvidia_client,
        trace_store=store
    )
    
    with patch.object(pipeline.schema_pruner, 'prune_schema') as mock_prune:
        mock_prune.return_value = {
            "tables": {"test": {"columns": [{"name": "id", "type": "int", "primary_key": True}]}}
        }
        
        with patch('app.sql_pipeline.SQLValidator.validate', return_value=(True, None)):
            res = pipeline.run_pipeline(
                job_id="job123",
                natural_query="get test"
            )
            
    # Success returned despite store raising exception
    assert res["success"] is True
    assert res["generated_sql"] == "SELECT\n  *\nFROM test"

def test_pipeline_trace_capture_sql_validation_failure(mock_schema_manager, mock_nvidia_client):
    store = RecordingTraceStore()
    pipeline = SQLGenerationPipeline(
        schema_manager=mock_schema_manager,
        nvidia_client=mock_nvidia_client,
        trace_store=store
    )
    
    mock_nvidia_client.generate_sql.return_value = "SELECT missing_col FROM test"
    
    with patch.object(pipeline.schema_pruner, 'prune_schema') as mock_prune:
        mock_prune.return_value = {
            "tables": {"test": {"columns": [{"name": "id", "type": "int", "primary_key": True}]}}
        }
        
        with patch('app.sql_pipeline.SQLValidator.validate', return_value=(False, "Missing column: missing_col")):
            res = pipeline.run_pipeline(
                job_id="job123",
                natural_query="get test",
                max_attempts=1
            )
            
    assert res["success"] is False
    assert len(store.saved) == 1
    
    trace = store.saved[0]
    assert trace.sql_valid is False
    assert trace.last_generated_sql is not None
    assert trace.generated_sql is None
    assert trace.error_type == "sql_generation_exhausted"
    assert len(trace.sql_validation_errors) == 1
    assert trace.sql_validation_errors[0]["type"] == "missing_column"
    assert trace.sql_validation_errors[0]["stage"] == "semantic_validation"
    assert len(trace.attempts) == 1
    assert trace.attempts[0]["valid"] is False

def test_pipeline_trace_clears_validation_errors_after_successful_retry(mock_schema_manager, mock_nvidia_client):
    store = RecordingTraceStore()
    pipeline = SQLGenerationPipeline(
        schema_manager=mock_schema_manager,
        nvidia_client=mock_nvidia_client,
        trace_store=store
    )
    
    mock_nvidia_client.generate_sql.side_effect = [
        "SELECT missing_col FROM test",
        "SELECT * FROM test",
    ]
    
    with patch.object(pipeline.schema_pruner, 'prune_schema') as mock_prune:
        mock_prune.return_value = {
            "tables": {"test": {"columns": [{"name": "id", "type": "int", "primary_key": True}]}}
        }
        
        with patch('app.sql_pipeline.SQLValidator.validate', side_effect=[
            (False, "Missing column: missing_col"),
            (True, None),
        ]):
            res = pipeline.run_pipeline(
                job_id="job123",
                natural_query="get test",
                max_attempts=2
            )
            
    assert res["success"] is True
    
    trace = store.saved[0]
    assert trace.sql_valid is True
    assert trace.generated_sql is not None
    assert trace.last_generated_sql == trace.generated_sql
    assert trace.sql_validation_errors == []
    assert len(trace.attempts) == 2
    assert trace.attempts[0]["valid"] is False
    assert trace.attempts[1]["valid"] is True

def test_pipeline_final_validation_errors_reflect_only_last_failed_attempt(mock_schema_manager, mock_nvidia_client):
    store = RecordingTraceStore()
    pipeline = SQLGenerationPipeline(
        schema_manager=mock_schema_manager,
        nvidia_client=mock_nvidia_client,
        trace_store=store
    )
    
    mock_nvidia_client.generate_sql.side_effect = [
        "SELECT missing_col FROM users",
        "DELETE FROM users;",
    ]
    
    with patch.object(pipeline.schema_pruner, 'prune_schema') as mock_prune:
        mock_prune.return_value = {
            "tables": {"users": {"columns": [{"name": "id", "type": "int", "primary_key": True}]}}
        }
        
        with patch('app.sql_pipeline.SQLValidator.validate', side_effect=[
            (False, "Missing column: missing_col"),
        ]):
            res = pipeline.run_pipeline(
                job_id="job123",
                natural_query="get users",
                max_attempts=2
            )
            
    trace = store.saved[0]
    
    assert trace.sql_valid is False
    assert trace.generated_sql is None
    assert trace.last_generated_sql == "DELETE FROM users;"
    assert len(trace.attempts) == 2
    
    assert trace.attempts[0]["validation_errors"][0]["stage"] == "semantic_validation"
    assert trace.attempts[1]["validation_errors"][0]["stage"] == "sql_guardrail"
    
    assert len(trace.sql_validation_errors) == 1
    assert trace.sql_validation_errors[0]["stage"] == "sql_guardrail"

def test_pipeline_trace_capture_unsafe_sql_fail_fast(mock_schema_manager, mock_nvidia_client):
    store = RecordingTraceStore()
    pipeline = SQLGenerationPipeline(
        schema_manager=mock_schema_manager,
        nvidia_client=mock_nvidia_client,
        trace_store=store
    )

    # First is unsafe, pipeline should fail-fast
    mock_nvidia_client.generate_sql.side_effect = [
        "DELETE FROM customers WHERE id = 1;",
        "SELECT * FROM customers WHERE id = 1;"
    ]

    with patch.object(pipeline.schema_pruner, 'prune_schema') as mock_prune:
        mock_prune.return_value = {
            "tables": {"customers": {"columns": [{"name": "id", "type": "int", "primary_key": True}]}}
        }

        with patch('app.sql_pipeline.SQLValidator.validate', return_value=(True, None)):
            res = pipeline.run_pipeline(
                job_id="job123",
                natural_query="get test",
                max_attempts=2
            )

    assert res["success"] is False
    assert len(res["attempts"]) == 1

    trace = store.saved[0]
    assert trace.sql_valid is False
    assert trace.generated_sql is None
    assert trace.last_generated_sql == "DELETE FROM customers WHERE id = 1;"
    assert trace.error_type == "sql_generation_exhausted"
    assert len(trace.attempts) == 1
    assert trace.attempts[0]["valid"] is False
    assert trace.attempts[0]["validation_errors"][0]["stage"] == "sql_guardrail"

def test_pipeline_trace_capture_unsafe_failure_fail_fast(mock_schema_manager, mock_nvidia_client):
    store = RecordingTraceStore()
    pipeline = SQLGenerationPipeline(
        schema_manager=mock_schema_manager,
        nvidia_client=mock_nvidia_client,
        trace_store=store
    )

    mock_nvidia_client.generate_sql.side_effect = [
        "DROP TABLE users;",
        "DELETE FROM users;"
    ]

    with patch.object(pipeline.schema_pruner, 'prune_schema') as mock_prune:
        mock_prune.return_value = {
            "tables": {"users": {"columns": [{"name": "id", "type": "int", "primary_key": True}]}}
        }

        with patch('app.sql_pipeline.SQLValidator.validate', return_value=(True, None)):
            res = pipeline.run_pipeline(
                job_id="job123",
                natural_query="get users",
                max_attempts=2
            )

    assert res["success"] is False

    trace = store.saved[0]
    assert trace.sql_valid is False
    assert trace.generated_sql is None
    assert trace.last_generated_sql == "DROP TABLE users;"
    assert trace.error_type == "sql_generation_exhausted"
    assert len(trace.attempts) == 1
    assert trace.attempts[0]["valid"] is False
    assert trace.attempts[0]["validation_errors"][0]["stage"] == "sql_guardrail"

def test_pipeline_trace_capture_multiple_statements_rejection(mock_schema_manager, mock_nvidia_client):
    store = RecordingTraceStore()
    pipeline = SQLGenerationPipeline(
        schema_manager=mock_schema_manager,
        nvidia_client=mock_nvidia_client,
        trace_store=store
    )
    
    mock_nvidia_client.generate_sql.return_value = "SELECT * FROM users; DELETE FROM users;"
    
    with patch.object(pipeline.schema_pruner, 'prune_schema') as mock_prune:
        mock_prune.return_value = {
            "tables": {"users": {"columns": [{"name": "id", "type": "int", "primary_key": True}]}}
        }
        
        with patch('app.sql_pipeline.SQLValidator.validate', return_value=(True, None)):
            res = pipeline.run_pipeline(
                job_id="job123",
                natural_query="get users",
                max_attempts=1
            )
            
    assert res["success"] is False
    trace = store.saved[0]
    
    error = trace.sql_validation_errors[0]
    assert error["type"] == "multiple_statements"
    assert error["stage"] == "sql_guardrail"

def test_pipeline_trace_schema_selection_exception(mock_schema_manager, mock_nvidia_client):
    store = RecordingTraceStore()
    pipeline = SQLGenerationPipeline(
        schema_manager=mock_schema_manager,
        nvidia_client=mock_nvidia_client,
        trace_store=store
    )
    
    with patch.object(pipeline.schema_pruner, 'prune_schema') as mock_prune:
        mock_prune.return_value = {
            "tables": {"test": {"columns": [{"name": "id", "type": "int", "primary_key": True}]}}
        }
        
        with patch("app.sql_pipeline.select_schema_context") as mock_selector:
            mock_selector.side_effect = Exception("Malformed context")
            
            res = pipeline.run_pipeline(
                job_id="job123",
                natural_query="get test"
            )
            
    assert res["success"] is False
    assert len(store.saved) == 1
    
    trace = store.saved[0]
    assert trace.error_type == "schema_context_selection_crashed"
    assert trace.schema_context_selection["selection_failed"] is True
    assert trace.schema_context_selection["error_type"] == "schema_context_selection_crashed"
    assert trace.generated_sql is None

def test_pipeline_fallback_is_traced(mock_schema_manager, mock_nvidia_client):
    store = RecordingTraceStore()
    pipeline = SQLGenerationPipeline(
        schema_manager=mock_schema_manager,
        nvidia_client=mock_nvidia_client,
        trace_store=store
    )
    
    mock_nvidia_client.generate_sql.return_value = "SELECT * FROM table1;"
    
    with patch.object(pipeline.schema_pruner, 'prune_schema') as mock_prune:
        mock_prune.return_value = {
            "tables": {
                "table1": {"columns": [{"name": "col1", "type": "int", "primary_key": True}]},
                "table2": {"columns": [{"name": "col2", "type": "int", "primary_key": True}]}
            }
        }
        
        with patch('app.sql_pipeline.SQLValidator.validate', return_value=(True, None)):
            # Wrap select_schema_context to inject max_tables=3 as requested in the PR
            from app.schema.schema_context_selector import select_schema_context
            def select_schema_context_wrapper(*args, **kwargs):
                kwargs['max_tables'] = 3
                return select_schema_context(*args, **kwargs)
                
            with patch('app.sql_pipeline.select_schema_context', side_effect=select_schema_context_wrapper):
                res = pipeline.run_pipeline(
                    job_id="job123",
                    natural_query="unrelated query matching nothing fallback trigger"
                )
            
    assert res["success"] is True
    assert len(store.saved) == 1
    
    trace = store.saved[0]
    
    assert trace.schema_context_selection["selector_version"] == "deterministic_v1"
    assert trace.schema_context_selection["fallback_used"] is True
    assert trace.schema_context_selection["fallback_strategy"] == "deterministic_bounded_fallback"
    assert trace.schema_context_selection["fallback_limit"] == 3
