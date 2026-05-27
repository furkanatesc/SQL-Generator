import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app, process_job_pipeline, verify_api_key

client = TestClient(app)

@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[verify_api_key] = lambda: True
    yield
    app.dependency_overrides.clear()

FAKE_JOB_PENDING = {
    "id": "job-123",
    "status": "processing",
    "natural_query": "show me users",
    "file_path": None,
    "previous_sql": None,
    "dialect": "postgres"
}

FAKE_JOB_FAILED = {
    "id": "job-failed-123",
    "status": "failed",
    "natural_query": "show me users",
    "previous_sql": None,
    "dialect": "postgres",
    "created_at": "2026-05-25T10:00:00Z",
    "result_sql": None,
    "error_message": "SQL üretimi başarısız oldu. 1 deneme yapıldı."
}

def assert_minimum_job_shape(job: dict):
    assert isinstance(job, dict)
    assert "id" in job
    assert "status" in job
    assert "natural_query" in job
    assert "previous_sql" in job
    assert "dialect" in job
    assert "created_at" in job
    assert "result_sql" in job
    assert "error_message" in job

@patch("app.database.get_job", return_value=FAKE_JOB_PENDING)
@patch("app.database.update_job_status")
@patch("app.database.get_config", return_value="postgres")
@patch("app.sql_pipeline.SQLGenerationPipeline.run_pipeline")
def test_process_job_pipeline_failure_does_not_persist_result_sql(
    mock_run_pipeline, mock_get_config, mock_update_job_status, mock_get_job
):
    mock_run_pipeline.return_value = {
        "success": False,
        "error": "SQL üretimi başarısız oldu. 1 deneme yapıldı.",
        "generated_sql": "",
        "attempts": []
    }
    
    process_job_pipeline("job-123")
    
    # Assert run_pipeline was called
    mock_run_pipeline.assert_called_once()
    
    # Assert update_job_status was called correctly
    # It is called twice: once for "processing", once for "failed"
    assert mock_update_job_status.call_count == 2
    
    # Get the last call (which should be the failure state update)
    args, kwargs = mock_update_job_status.call_args_list[-1]
    assert args[0] == "job-123"
    assert args[1] == "failed"
    assert "error_message" in kwargs
    assert kwargs["error_message"] == "SQL üretimi başarısız oldu. 1 deneme yapıldı."
    assert "result_sql" not in kwargs

@patch("app.database.get_job", return_value=FAKE_JOB_PENDING)
@patch("app.database.update_job_status")
@patch("app.database.get_config", return_value="postgres")
@patch("app.sql_pipeline.SQLGenerationPipeline.run_pipeline")
def test_process_job_pipeline_guardrail_failure_never_exposes_unsafe_sql_as_result(
    mock_run_pipeline, mock_get_config, mock_update_job_status, mock_get_job
):
    # Simulating a guardrail failure which has unsafe SQL in attempts
    mock_run_pipeline.return_value = {
        "success": False,
        "error": "Guardrail Error",
        "generated_sql": "",
        "attempts": [
            {
                "sql": "DROP TABLE users;",
                "valid": False,
                "validation_errors": [{"stage": "sql_guardrail", "message": "Unsafe SQL"}]
            }
        ]
    }
    
    process_job_pipeline("job-123")
    
    # Assert the last update call for failure
    args, kwargs = mock_update_job_status.call_args_list[-1]
    assert args[0] == "job-123"
    assert args[1] == "failed"
    assert "error_message" in kwargs
    assert kwargs["error_message"] == "Guardrail Error"
    
    # Enforce unsafe SQL is NEVER exposed in the persistence layer
    assert "result_sql" not in kwargs

@patch("app.main.get_job", return_value=FAKE_JOB_FAILED)
def test_get_failed_job_detail_response_is_safe(mock_get_job):
    response = client.get("/api/jobs/job-failed-123")
    assert response.status_code == 200
    
    data = response.json()
    assert_minimum_job_shape(data)
    assert data["status"] == "failed"
    assert data["error_message"] == "SQL üretimi başarısız oldu. 1 deneme yapıldı."
    assert data["result_sql"] is None

@patch("app.database.get_job", return_value=FAKE_JOB_PENDING)
@patch("app.database.update_job_status")
@patch("app.database.get_config", return_value="postgres")
@patch("app.sql_pipeline.SQLGenerationPipeline.run_pipeline")
def test_process_job_pipeline_success_still_persists_result_sql(
    mock_run_pipeline, mock_get_config, mock_update_job_status, mock_get_job
):
    mock_run_pipeline.return_value = {
        "success": True,
        "error": None,
        "generated_sql": "SELECT * FROM users;",
        "attempts": []
    }
    
    process_job_pipeline("job-123")
    
    # Assert the last update call for success
    args, kwargs = mock_update_job_status.call_args_list[-1]
    assert args[0] == "job-123"
    assert args[1] == "completed"
    assert "result_sql" in kwargs
    assert kwargs["result_sql"] == "SELECT * FROM users;"
    assert "error_message" not in kwargs
