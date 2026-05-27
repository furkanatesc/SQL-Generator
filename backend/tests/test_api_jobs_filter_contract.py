import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app, verify_api_key

client = TestClient(app)


@pytest.fixture(autouse=True)
def override_auth():
    app.dependency_overrides[verify_api_key] = lambda: True
    yield
    app.dependency_overrides.clear()


# Helper function strictly validating standard error response contract from PR 11.2
def assert_error_contract(body, *, code):
    assert set(body.keys()) == {"error"}
    assert set(body["error"].keys()) == {"code", "message", "details"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str)


# 1. No status filter default contract test
@patch("app.main.list_jobs", return_value=[
    {"id": "job-1", "status": "completed"},
    {"id": "job-2", "status": "pending"},
])
def test_jobs_list_without_status_filter_preserves_default_contract(mock_list):
    res = client.get("/api/jobs")

    assert res.status_code == 200
    body = res.json()

    assert set(body.keys()) == {"jobs", "limit", "offset", "count", "status"}
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert body["count"] == 2
    assert body["status"] is None
    assert len(body["jobs"]) == 2

    mock_list.assert_called_once_with(limit=50, offset=0, status=None)


# 2. Filter by pending status
@patch("app.main.list_jobs", return_value=[
    {"id": "job-2", "status": "pending"},
])
def test_jobs_list_filters_by_pending_status(mock_list):
    res = client.get("/api/jobs?status=pending")

    assert res.status_code == 200
    body = res.json()

    assert body["status"] == "pending"
    assert body["count"] == 1
    assert body["jobs"][0]["status"] == "pending"

    mock_list.assert_called_once_with(limit=50, offset=0, status="pending")


# 3. Filter by completed status
@patch("app.main.list_jobs", return_value=[
    {"id": "job-1", "status": "completed"},
])
def test_jobs_list_filters_by_completed_status(mock_list):
    res = client.get("/api/jobs?status=completed")

    assert res.status_code == 200
    body = res.json()

    assert body["status"] == "completed"
    assert body["count"] == 1
    assert body["jobs"][0]["status"] == "completed"

    mock_list.assert_called_once_with(limit=50, offset=0, status="completed")


# 4. Reject invalid status (returns 422 standard error envelope)
def test_jobs_list_rejects_invalid_status():
    res = client.get("/api/jobs?status=unknown")

    assert res.status_code == 422
    body = res.json()

    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "status" in str(body["error"]["details"])


# 5. OpenAPI verification for status query parameter
def test_openapi_jobs_status_query_parameter_contract():
    schema = client.get("/openapi.json").json()
    parameters = schema["paths"]["/api/jobs"]["get"]["parameters"]
    
    # Extract status parameter
    status_param = next(p for p in parameters if p["name"] == "status")
    
    # Assert status parameter contract
    assert status_param["in"] == "query"
    assert status_param["required"] is False
    assert status_param["schema"]["anyOf"][0]["$ref"] == "#/components/schemas/JobStatus"


# 6. OpenAPI verification for JobsListResponse status filter metadata
def test_openapi_jobs_list_response_includes_status_filter_metadata():
    schema = client.get("/openapi.json").json()
    components = schema["components"]["schemas"]
    
    assert "JobsListResponse" in components
    jobs_list_schema = components["JobsListResponse"]
    
    # Assert required fields include status
    required_fields = set(jobs_list_schema["required"])
    assert "status" in required_fields
    
    # Assert status type/ref
    properties = jobs_list_schema["properties"]
    assert "anyOf" in properties["status"]
    refs = [item["$ref"] for item in properties["status"]["anyOf"] if "$ref" in item]
    assert "#/components/schemas/JobStatus" in refs
