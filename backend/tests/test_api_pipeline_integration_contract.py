import pytest
from unittest.mock import MagicMock, patch, call

from app.main import process_job_pipeline


@patch("app.trace.dependencies.get_trace_store")
@patch("app.sql_pipeline.SQLGenerationPipeline")
@patch("app.database.update_job_status")
@patch("app.database.get_config")
@patch("app.database.get_job")
def test_process_job_pipeline_passes_job_fields_to_pipeline(
    mock_get_job, mock_get_config, mock_update, mock_pipeline_cls, mock_trace
):
    # Fake job
    mock_get_job.return_value = {
        "id": "job-123",
        "status": "pending",
        "file_path": None,
        "natural_query": "show me users",
        "previous_sql": "SELECT 1"
    }

    # config returns
    def config_side_effect(key):
        if key == "target_db_type": return "postgres"
        if key == "nvidia_api_key": return "fake-key"
        return None
    mock_get_config.side_effect = config_side_effect
    
    mock_pipeline_inst = MagicMock()
    mock_pipeline_cls.return_value = mock_pipeline_inst
    mock_pipeline_inst.run_pipeline.return_value = {"success": True, "generated_sql": "SELECT *", "error": None}
    
    mock_trace.return_value = MagicMock()
    
    process_job_pipeline("job-123")
    
    # Assert run_pipeline is called with right args
    mock_pipeline_inst.run_pipeline.assert_called_once()
    kwargs = mock_pipeline_inst.run_pipeline.call_args.kwargs
    assert kwargs["job_id"] == "job-123"
    assert kwargs["natural_query"] == "show me users"
    assert kwargs["previous_sql"] == "SELECT 1"
    assert kwargs["excel_file_path"] is None
    assert kwargs["dialect"] == "postgres"
    assert kwargs["api_key"] == "fake-key"
    assert "log_callback" in kwargs
    
    # Check status update to completed
    mock_update.assert_any_call("job-123", "completed", result_sql="SELECT *")


@patch("app.trace.dependencies.get_trace_store")
@patch("app.sql_pipeline.SQLGenerationPipeline")
@patch("app.database.update_job_status")
@patch("app.database.get_config")
@patch("app.database.get_job")
def test_process_job_pipeline_uses_postgres_when_dialect_config_missing(
    mock_get_job, mock_get_config, mock_update, mock_pipeline_cls, mock_trace
):
    mock_get_job.return_value = {
        "id": "job-123",
        "status": "pending",
        "file_path": None,
        "natural_query": "show me users",
        "previous_sql": None
    }

    def config_side_effect(key):
        if key == "target_db_type": return None  # Missing config
        if key == "nvidia_api_key": return "fake-key"
        return None
    mock_get_config.side_effect = config_side_effect
    
    mock_pipeline_inst = MagicMock()
    mock_pipeline_cls.return_value = mock_pipeline_inst
    mock_pipeline_inst.run_pipeline.return_value = {"success": True, "generated_sql": "SELECT *", "error": None}
    
    process_job_pipeline("job-123")
    
    kwargs = mock_pipeline_inst.run_pipeline.call_args.kwargs
    assert kwargs["dialect"] == "postgres"


@patch("app.trace.dependencies.get_trace_store")
@patch("app.sql_pipeline.SQLGenerationPipeline")
@patch("app.database.update_job_status")
@patch("app.database.get_config")
@patch("app.database.get_job")
def test_process_job_pipeline_uses_api_key_fallback_when_nvidia_key_missing(
    mock_get_job, mock_get_config, mock_update, mock_pipeline_cls, mock_trace
):
    mock_get_job.return_value = {
        "id": "job-123",
        "status": "pending",
        "file_path": None,
        "natural_query": "show me users",
        "previous_sql": None
    }

    def config_side_effect(key):
        if key == "target_db_type": return "postgres"
        if key == "nvidia_api_key": return None  # Missing nvidia_api_key
        if key == "api_key": return "fallback-key"
        return None
    mock_get_config.side_effect = config_side_effect
    
    mock_pipeline_inst = MagicMock()
    mock_pipeline_cls.return_value = mock_pipeline_inst
    mock_pipeline_inst.run_pipeline.return_value = {"success": True, "generated_sql": "SELECT *", "error": None}
    
    process_job_pipeline("job-123")
    
    kwargs = mock_pipeline_inst.run_pipeline.call_args.kwargs
    assert kwargs["api_key"] == "fallback-key"


@patch("app.trace.dependencies.get_trace_store")
@patch("app.sql_pipeline.SQLGenerationPipeline")
@patch("app.database.update_job_status")
@patch("app.database.get_config")
@patch("app.database.get_job")
def test_process_job_pipeline_does_not_persist_after_cancelled_job(
    mock_get_job, mock_get_config, mock_update, mock_pipeline_cls, mock_trace
):
    mock_job_initial = {
        "id": "job-123",
        "status": "processing",
        "file_path": None,
        "natural_query": "test",
        "previous_sql": None
    }
    
    mock_job_cancelled = {
        "id": "job-123",
        "status": "cancelled",
        "file_path": None,
        "natural_query": "test",
        "previous_sql": None
    }
    
    call_count = 0
    def mock_get_job_side_effect(job_id):
        nonlocal call_count
        call_count += 1
        # Ilk cagri: is baslangici, ikinci cagri: pipeline sonrasi
        if call_count == 1:
            return mock_job_initial
        return mock_job_cancelled

    mock_get_job.side_effect = mock_get_job_side_effect
    
    def config_side_effect(key):
        if key == "target_db_type": return "postgres"
        if key == "nvidia_api_key": return "fake-key"
        return None
    mock_get_config.side_effect = config_side_effect
    
    mock_pipeline_inst = MagicMock()
    mock_pipeline_cls.return_value = mock_pipeline_inst
    mock_pipeline_inst.run_pipeline.return_value = {"success": True, "generated_sql": "SELECT *", "error": None}
    
    process_job_pipeline("job-123")
    
    # Pipeline calls
    mock_pipeline_inst.run_pipeline.assert_called_once()
    
    # Assert final status update is NOT called
    for call_obj in mock_update.call_args_list:
        args = call_obj[0]
        if len(args) > 1:
            status = args[1]
            assert status not in ["completed", "failed"], "Should not overwrite cancellation state"


@patch("app.trace.dependencies.get_trace_store")
@patch("app.sql_pipeline.SQLGenerationPipeline")
@patch("app.database.update_job_status")
@patch("app.database.get_config")
@patch("app.database.get_job")
def test_process_job_pipeline_marks_processing_before_pipeline_run(
    mock_get_job, mock_get_config, mock_update, mock_pipeline_cls, mock_trace
):
    mock_get_job.return_value = {
        "id": "job-123",
        "status": "pending",
        "file_path": None,
        "natural_query": "test",
        "previous_sql": None
    }
    
    mock_get_config.return_value = "fake"
    
    mock_manager = MagicMock()
    
    mock_pipeline_inst = MagicMock()
    mock_pipeline_cls.return_value = mock_pipeline_inst
    mock_pipeline_inst.run_pipeline.return_value = {"success": True, "generated_sql": "SELECT *", "error": None}
    
    mock_manager.attach_mock(mock_update, "update")
    mock_manager.attach_mock(mock_pipeline_inst.run_pipeline, "run_pipeline")
    
    process_job_pipeline("job-123")
    
    calls = mock_manager.mock_calls
    first_update = None
    first_run = None
    
    for i, c in enumerate(calls):
        if c[0] == "update" and len(c[1]) > 1 and c[1][1] == "processing" and first_update is None:
            first_update = i
        if c[0] == "run_pipeline" and first_run is None:
            first_run = i
            
    assert first_update is not None, "Should mark as processing"
    assert first_run is not None, "Should run pipeline"
    assert first_update < first_run, "Must mark processing BEFORE pipeline run"
