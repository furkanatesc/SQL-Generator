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
    "id": "job-val-1234",
    "status": "pending",
    "natural_query": "show me users",
    "previous_sql": None,
    "dialect": "postgres",
    "created_at": "2026-05-25T10:00:00Z",
    "result_sql": None,
    "error_message": None
}

def test_create_job_without_file_rejects_missing_natural_query():
    with patch("app.main.create_job") as mock_create_job, \
         patch("app.main.process_job_pipeline") as mock_process_job_pipeline:
        
        response = client.post("/api/jobs/without-file", json={})
        
        assert response.status_code == 422
        mock_create_job.assert_not_called()
        mock_process_job_pipeline.assert_not_called()

def test_create_job_without_file_rejects_null_natural_query():
    with patch("app.main.create_job") as mock_create_job, \
         patch("app.main.process_job_pipeline") as mock_process_job_pipeline:
        
        response = client.post("/api/jobs/without-file", json={"natural_query": None})
        
        assert response.status_code == 422
        mock_create_job.assert_not_called()
        mock_process_job_pipeline.assert_not_called()

def test_create_job_without_file_rejects_empty_natural_query():
    with patch("app.main.create_job") as mock_create_job, \
         patch("app.main.process_job_pipeline") as mock_process_job_pipeline:
        
        response = client.post("/api/jobs/without-file", json={"natural_query": ""})
        
        assert response.status_code in [400, 422]
        mock_create_job.assert_not_called()
        mock_process_job_pipeline.assert_not_called()

def test_create_job_without_file_rejects_whitespace_natural_query():
    with patch("app.main.create_job") as mock_create_job, \
         patch("app.main.process_job_pipeline") as mock_process_job_pipeline:
        
        response = client.post("/api/jobs/without-file", json={"natural_query": "   "})
        
        assert response.status_code in [400, 422]
        mock_create_job.assert_not_called()
        mock_process_job_pipeline.assert_not_called()

def test_create_job_without_file_accepts_valid_request_without_previous_sql():
    with patch("app.main.create_job", return_value=FAKE_JOB) as mock_create_job, \
         patch("app.main.process_job_pipeline") as mock_process_job_pipeline, \
         patch("app.main.get_config", return_value="postgres"):
        
        response = client.post("/api/jobs/without-file", json={"natural_query": "show me users"})
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert "job" in data
        
        mock_create_job.assert_called_once()
        args, kwargs = mock_create_job.call_args
        assert kwargs["natural_query"] == "show me users"
        assert kwargs["previous_sql"] is None
        
        mock_process_job_pipeline.assert_called_once()

def test_create_job_without_file_accepts_valid_request_with_previous_sql():
    with patch("app.main.create_job", return_value=FAKE_JOB) as mock_create_job, \
         patch("app.main.process_job_pipeline") as mock_process_job_pipeline, \
         patch("app.main.get_config", return_value="postgres"):
        
        response = client.post(
            "/api/jobs/without-file", 
            json={"natural_query": "show me users", "previous_sql": "SELECT 1"}
        )
        
        assert response.status_code == 200
        
        mock_create_job.assert_called_once()
        args, kwargs = mock_create_job.call_args
        assert kwargs["natural_query"] == "show me users"
        assert kwargs["previous_sql"] == "SELECT 1"
        
        mock_process_job_pipeline.assert_called_once()
