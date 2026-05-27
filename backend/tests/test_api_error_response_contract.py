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


# Helper function strictly validating standard error response contract
def assert_error_contract(body, *, code):
    assert set(body.keys()) == {"error"}
    assert set(body["error"].keys()) == {"code", "message", "details"}
    assert body["error"]["code"] == code
    assert isinstance(body["error"]["message"], str)


# 1. Standard 404 error envelope when configuration key is missing
@patch("app.main.get_config", return_value=None)
def test_missing_config_returns_standard_404_error(mock_get):
    res = client.get("/api/configs/non_existent_key")
    assert res.status_code == 404
    body = res.json()
    assert_error_contract(body, code="NOT_FOUND")
    assert body["error"]["details"] is None
    assert "not found" in body["error"]["message"].lower()


# 2. Standard 404 error envelope when job ID is missing
@patch("app.main.get_job", return_value=None)
def test_missing_job_returns_standard_404_error(mock_get):
    res = client.get("/api/jobs/non_existent_job_id")
    assert res.status_code == 404
    body = res.json()
    assert_error_contract(body, code="NOT_FOUND")
    assert body["error"]["details"] is None
    assert "not found" in body["error"]["message"].lower()


# 3. Standard 400 error envelope when trying to cancel job in final state
@patch("app.main.get_job", return_value={"id": "job-123", "status": "completed"})
def test_cancel_final_state_returns_standard_400_error(mock_get):
    res = client.post("/api/jobs/job-123/cancel")
    assert res.status_code == 400
    body = res.json()
    assert_error_contract(body, code="BAD_REQUEST")
    assert body["error"]["details"] is None
    assert "final state" in body["error"]["message"].lower()


# 4. Standard 422 error envelope on blank/whitespace natural query (HTTPException raised)
def test_blank_natural_query_returns_standard_422_error():
    res = client.post(
        "/api/jobs/without-file",
        json={"natural_query": "   "}
    )
    assert res.status_code == 422
    body = res.json()
    assert_error_contract(body, code="VALIDATION_ERROR")
    assert isinstance(body["error"]["details"], list)
    assert "natural_query" in str(body["error"]["details"])


# 5. Standard 422 error envelope on missing required field (RequestValidationError raised)
def test_missing_required_field_returns_standard_422_error():
    # Sending empty body (natural_query field is missing)
    res = client.post(
        "/api/jobs/without-file",
        json={}
    )
    assert res.status_code == 422
    body = res.json()
    assert_error_contract(body, code="VALIDATION_ERROR")
    
    # Assert validation details structure and elements
    assert isinstance(body["error"]["details"], list)
    error_details = body["error"]["details"][0]
    assert "natural_query" in error_details["loc"]
    assert error_details["type"] == "missing"


# 6. Standard 400 error envelope when uploading file with invalid extension
def test_invalid_upload_extension_returns_standard_400_error():
    import io
    file_obj = io.BytesIO(b"fake text content")
    res = client.post(
        "/api/files/upload",
        files={"file": ("test_file.txt", file_obj, "text/plain")},
        data={"natural_query": "load from text"}
    )
    assert res.status_code == 400
    body = res.json()
    assert_error_contract(body, code="BAD_REQUEST")
    assert body["error"]["details"] is None
    assert "only excel files" in body["error"]["message"].lower()


# 7. OpenAPI verification: contains exact ErrorResponse & ErrorBody schemas
def test_openapi_contains_error_response_schema():
    schema = client.get("/openapi.json").json()
    components = schema["components"]["schemas"]
    
    # Assert existence
    assert "ErrorResponse" in components
    assert "ErrorBody" in components

    # Assert ErrorResponse schema properties
    error_response_schema = components["ErrorResponse"]
    assert set(error_response_schema["required"]) == {"error"}
    assert error_response_schema["properties"]["error"]["$ref"] == "#/components/schemas/ErrorBody"

    # Assert ErrorBody schema properties
    error_body_schema = components["ErrorBody"]
    assert set(error_body_schema["required"]) == {"code", "message"}
    assert error_body_schema["properties"]["code"]["type"] == "string"
    assert error_body_schema["properties"]["message"]["type"] == "string"


# 8. Auth failure: Missing API key
def test_missing_api_key_returns_standard_403_error():
    app.dependency_overrides.clear()

    res = client.get("/api/jobs")

    assert res.status_code == 403
    body = res.json()
    assert_error_contract(body, code="FORBIDDEN")
    assert body["error"]["details"] is None
    assert "api key" in body["error"]["message"].lower()


# 9. Auth failure: Invalid API key
@patch("app.auth.get_config", return_value="expected-key")
def test_invalid_api_key_returns_standard_403_error(mock_get_config):
    app.dependency_overrides.clear()

    res = client.get("/api/jobs", headers={"X-API-Key": "wrong-key"})

    assert res.status_code == 403
    body = res.json()
    assert_error_contract(body, code="FORBIDDEN")
    assert body["error"]["details"] is None
    assert "invalid api key" in body["error"]["message"].lower()


# 10. Auth failure: API Key not configured
@patch("app.auth.get_config", return_value=None)
def test_api_key_not_configured_returns_standard_500_error(mock_get_config):
    app.dependency_overrides.clear()

    res = client.get("/api/jobs", headers={"X-API-Key": "some-key"})

    assert res.status_code == 500
    body = res.json()
    assert_error_contract(body, code="INTERNAL_SERVER_ERROR")
    assert body["error"]["details"] is None
    assert "not configured" in body["error"]["message"].lower()


# 11. OpenAPI: Endpoint-level error response Ref lock
def test_openapi_endpoints_expose_error_response():
    schema = client.get("/openapi.json").json()
    
    def assert_error_response_ref(schema, method, path, status_code):
        response = schema["paths"][path][method]["responses"][str(status_code)]
        ref = response["content"]["application/json"]["schema"]["$ref"]
        assert ref == "#/components/schemas/ErrorResponse"
        
    assert_error_response_ref(schema, "get", "/api/configs/{key}", 404)
    assert_error_response_ref(schema, "post", "/api/files/upload", 400)
    assert_error_response_ref(schema, "post", "/api/jobs/without-file", 422)
    assert_error_response_ref(schema, "get", "/api/jobs/{job_id}", 404)
    assert_error_response_ref(schema, "post", "/api/jobs/{job_id}/cancel", 400)
    assert_error_response_ref(schema, "post", "/api/jobs/{job_id}/cancel", 404)
