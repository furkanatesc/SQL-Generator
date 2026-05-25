import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app, verify_api_key

client = TestClient(app)

@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[verify_api_key] = lambda: True
    yield
    app.dependency_overrides.clear()

FAKE_JOB = {
    "job_id": "job-1234",
    "status": "pending",
    "natural_query": "show me users",
    "previous_sql": None,
    "dialect": "postgres",
    "created_at": "2026-05-25T10:00:00Z",
    "result_sql": None,
    "error_message": None
}

def assert_minimum_job_shape(job: dict):
    """
    Asserts that the provided job dictionary conforms to the required minimum API shape contract.
    """
    assert isinstance(job, dict)
    assert "job_id" in job
    assert "status" in job
    assert "natural_query" in job
    assert "previous_sql" in job
    assert "dialect" in job
    assert "created_at" in job
    assert "result_sql" in job
    assert "error_message" in job

@patch("app.main.get_config", return_value="postgres")
@patch("app.main.create_job", return_value=FAKE_JOB)
@patch("app.main.process_job_pipeline")
def test_create_job_without_file_response_shape(mock_process, mock_create, mock_config):
    response = client.post(
        "/api/jobs/without-file",
        json={"natural_query": "show me users"}
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Assert top-level shape
    assert "status" in data
    assert data["status"] == "success"
    assert "job" in data
    
    # Assert job shape
    assert_minimum_job_shape(data["job"])
    assert data["job"]["job_id"] == "job-1234"
    
    # Ensure background task was added but not actually executed synchronously
    # Background tasks in TestClient are executed after response is sent if we don't mock it,
    # but since we mocked process_job_pipeline, it won't do anything real.
    # Actually, BackgroundTasks are executed by TestClient, so mock_process WILL be called.
    assert mock_process.called

@patch("app.main.get_job", return_value=FAKE_JOB)
def test_get_job_detail_response_shape(mock_get_job):
    response = client.get("/api/jobs/job-1234")
    
    assert response.status_code == 200
    data = response.json()
    
    # GET /api/jobs/{job_id} returns the raw job object directly
    assert_minimum_job_shape(data)
    assert data["job_id"] == "job-1234"
    assert mock_get_job.called

@patch("app.main.list_jobs", return_value=[FAKE_JOB, FAKE_JOB])
def test_get_jobs_list_response_shape(mock_list_jobs):
    response = client.get("/api/jobs")
    
    assert response.status_code == 200
    data = response.json()
    
    # Assert top-level shape
    assert "jobs" in data
    assert isinstance(data["jobs"], list)
    assert len(data["jobs"]) == 2
    
    # Assert every job in the list conforms to shape
    for job in data["jobs"]:
        assert_minimum_job_shape(job)

@patch("app.main.get_job", return_value=None)
def test_get_job_detail_not_found_shape(mock_get_job):
    response = client.get("/api/jobs/non-existent-job")
    
    assert response.status_code == 404
    data = response.json()
    
    # Assert FastAPI standard HTTP exception contract
    assert "detail" in data
    assert "not found" in data["detail"].lower()
