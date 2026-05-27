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


# 1. Default pagination response contract test
@patch("app.main.list_jobs", return_value=[
    {"id": "job-1", "status": "completed"},
    {"id": "job-2", "status": "pending"},
])
def test_jobs_list_default_pagination_contract(mock_list):
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


# 2. Custom limit/offset pagination contract test
@patch("app.main.list_jobs", return_value=[
    {"id": "job-3", "status": "completed"},
])
def test_jobs_list_custom_limit_offset_contract(mock_list):
    res = client.get("/api/jobs?limit=10&offset=20")

    assert res.status_code == 200
    body = res.json()

    assert body["limit"] == 10
    assert body["offset"] == 20
    assert body["count"] == 1
    assert body["status"] is None

    mock_list.assert_called_once_with(limit=10, offset=20, status=None)


# 3. Reject limit below min
def test_jobs_list_rejects_limit_below_min():
    res = client.get("/api/jobs?limit=0")

    assert res.status_code == 422
    body = res.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "limit" in str(body["error"]["details"])


# 4. Reject limit above max
def test_jobs_list_rejects_limit_above_max():
    res = client.get("/api/jobs?limit=101")

    assert res.status_code == 422
    body = res.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "limit" in str(body["error"]["details"])


# 5. Reject negative offset
def test_jobs_list_rejects_negative_offset():
    res = client.get("/api/jobs?offset=-1")

    assert res.status_code == 422
    body = res.json()
    assert body["error"]["code"] == "VALIDATION_ERROR"
    assert "offset" in str(body["error"]["details"])


# 6. OpenAPI verification for jobs query parameters
def test_openapi_jobs_query_parameters_contract():
    schema = client.get("/openapi.json").json()
    parameters = schema["paths"]["/api/jobs"]["get"]["parameters"]
    
    # Extract limit and offset parameters
    limit_param = next(p for p in parameters if p["name"] == "limit")
    offset_param = next(p for p in parameters if p["name"] == "offset")
    
    # Assert limit parameter contract
    assert limit_param["in"] == "query"
    assert limit_param["required"] is False
    assert limit_param["schema"]["type"] == "integer"
    assert limit_param["schema"]["default"] == 50
    assert limit_param["schema"]["minimum"] == 1
    assert limit_param["schema"]["maximum"] == 100
    
    # Assert offset parameter contract
    assert offset_param["in"] == "query"
    assert offset_param["required"] is False
    assert offset_param["schema"]["type"] == "integer"
    assert offset_param["schema"]["default"] == 0
    assert offset_param["schema"]["minimum"] == 0


# 7. OpenAPI verification for JobsListResponse required fields
def test_openapi_jobs_list_response_pagination_fields():
    schema = client.get("/openapi.json").json()
    components = schema["components"]["schemas"]
    
    assert "JobsListResponse" in components
    jobs_list_schema = components["JobsListResponse"]
    
    # Assert required fields
    required_fields = set(jobs_list_schema["required"])
    assert required_fields == {"jobs", "limit", "offset", "count", "status"}
    
    # Assert property types
    properties = jobs_list_schema["properties"]
    assert properties["jobs"]["type"] == "array"
    assert properties["jobs"]["items"]["$ref"] == "#/components/schemas/JobDetailResponse"
    assert properties["limit"]["type"] == "integer"
    assert properties["offset"]["type"] == "integer"
    assert properties["count"]["type"] == "integer"
