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


# 1. Exact health response envelope contract test
def test_health_response_exact_contract():
    res = client.get("/health")
    assert res.status_code == 200
    body = res.json()
    assert body == {
        "status": "ok",
        "version": "0.1.0",
        "database": "SQLite ready",
    }


# 2. Response envelope structure contract for job creation without file
@patch("app.main.get_config", return_value="postgres")
@patch("app.main.create_job", return_value={"id": "job-123", "status": "pending"})
@patch("app.main.process_job_pipeline")
def test_create_job_without_file_response_envelope_contract(mock_process, mock_create, mock_config):
    res = client.post(
        "/api/jobs/without-file",
        json={"natural_query": "SELECT * FROM users"}
    )
    assert res.status_code == 200
    body = res.json()
    assert set(body.keys()) == {"status", "job"}
    assert body["status"] == "success"
    assert isinstance(body["job"], dict)
    assert body["job"]["id"] == "job-123"


# 3. Negatif request validation: blank/whitespace queries rejected with 422
def test_create_job_without_file_rejects_blank_natural_query():
    # Empty query
    res = client.post(
        "/api/jobs/without-file",
        json={"natural_query": ""}
    )
    assert res.status_code == 422

    # Whitespace only query
    res = client.post(
        "/api/jobs/without-file",
        json={"natural_query": "   "}
    )
    assert res.status_code == 422


# 4. Jobs list response envelope contract test
@patch("app.main.list_jobs", return_value=[{"id": "job-123", "status": "pending"}, {"id": "job-456", "status": "completed"}])
def test_jobs_list_response_envelope_contract(mock_list):
    res = client.get("/api/jobs")
    assert res.status_code == 200
    body = res.json()
    assert set(body.keys()) == {"jobs"}
    assert isinstance(body["jobs"], list)
    assert len(body["jobs"]) == 2
    assert body["jobs"][0]["id"] == "job-123"


# 5. Config get response contract test
@patch("app.main.get_config", return_value="some_value")
def test_config_get_response_contract(mock_get):
    res = client.get("/api/configs/target_db_type")
    assert res.status_code == 200
    body = res.json()
    assert body == {
        "key": "target_db_type",
        "value": "some_value"
    }


# 6. Config post response contract test
@patch("app.main.set_config")
def test_config_post_response_contract(mock_set):
    res = client.post("/api/configs/target_db_type", json={"value": "mysql"})
    assert res.status_code == 200
    body = res.json()
    assert body == {
        "status": "success",
        "key": "target_db_type",
        "value": "mysql"
    }


# 7. Job details retrieval behavior contract test
@patch("app.main.get_job", return_value={"id": "job-123", "status": "processing", "dialect": "sqlite", "created_at": "2026-05-27T10:00:00"})
def test_get_job_detail_response_contract(mock_get):
    res = client.get("/api/jobs/job-123")
    assert res.status_code == 200
    body = res.json()
    assert body["id"] == "job-123"
    assert body["status"] == "processing"
    assert body["dialect"] == "sqlite"
    assert body["created_at"] == "2026-05-27T10:00:00"


# 8. Job cancel execution behavior contract test
@patch("app.main.get_job", return_value={"id": "job-123", "status": "processing"})
@patch("app.main.update_job_status", return_value={"id": "job-123", "status": "cancelled", "created_at": "2026-05-27T10:00:00"})
def test_cancel_job_response_contract(mock_update, mock_get):
    res = client.post("/api/jobs/job-123/cancel")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "success"
    assert body["message"] == "Job cancellation requested."
    assert body["job"]["id"] == "job-123"
    assert body["job"]["status"] == "cancelled"


# 9. Excel File upload behavior contract test
@patch("app.main.get_config", return_value="postgres")
@patch("app.main.create_job", return_value={"id": "job-excel", "status": "pending", "file_path": "/tmp/excel.xlsx"})
@patch("app.main.process_job_pipeline")
def test_file_upload_response_contract(mock_process, mock_create, mock_config):
    import io
    file_content = b"fake excel file bytes"
    file_obj = io.BytesIO(file_content)
    res = client.post(
        "/api/files/upload",
        files={"file": ("test_file.xlsx", file_obj, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        data={"natural_query": "load from excel"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "success"
    assert "File uploaded successfully" in body["message"]
    assert body["job"]["id"] == "job-excel"
    assert body["job"]["status"] == "pending"


# 10. Verify OpenAPI schema contains response models and exact required properties/references
def test_openapi_has_response_models_for_public_endpoints():
    schema = client.get("/openapi.json").json()

    # /health path response
    health = schema["paths"]["/health"]["get"]["responses"]["200"]
    assert "schema" in health["content"]["application/json"]
    ref_health = health["content"]["application/json"]["schema"]["$ref"]
    assert "HealthResponse" in ref_health

    # /api/configs/{key} path response (GET)
    config_get = schema["paths"]["/api/configs/{key}"]["get"]["responses"]["200"]
    assert "schema" in config_get["content"]["application/json"]
    ref_config_get = config_get["content"]["application/json"]["schema"]["$ref"]
    assert "ConfigResponse" in ref_config_get

    # /api/configs/{key} path response (POST)
    config_post = schema["paths"]["/api/configs/{key}"]["post"]["responses"]["200"]
    assert "schema" in config_post["content"]["application/json"]
    ref_config_post = config_post["content"]["application/json"]["schema"]["$ref"]
    assert "ConfigUpdateResponse" in ref_config_post

    # /api/jobs/without-file path response (POST)
    job_post = schema["paths"]["/api/jobs/without-file"]["post"]["responses"]["200"]
    assert "schema" in job_post["content"]["application/json"]
    ref_job_post = job_post["content"]["application/json"]["schema"]["$ref"]
    assert "JobEnvelopeResponse" in ref_job_post

    # /api/jobs path response (GET)
    jobs_get = schema["paths"]["/api/jobs"]["get"]["responses"]["200"]
    assert "schema" in jobs_get["content"]["application/json"]
    ref_jobs_get = jobs_get["content"]["application/json"]["schema"]["$ref"]
    assert "JobsListResponse" in ref_jobs_get

    # /api/jobs/{job_id} path response (GET)
    job_detail = schema["paths"]["/api/jobs/{job_id}"]["get"]["responses"]["200"]
    assert "schema" in job_detail["content"]["application/json"]
    ref_job_detail = job_detail["content"]["application/json"]["schema"]["$ref"]
    assert "JobDetailResponse" in ref_job_detail

    # /api/jobs/{job_id}/cancel path response (POST)
    job_cancel = schema["paths"]["/api/jobs/{job_id}/cancel"]["post"]["responses"]["200"]
    assert "schema" in job_cancel["content"]["application/json"]
    ref_job_cancel = job_cancel["content"]["application/json"]["schema"]["$ref"]
    assert "CancelJobResponse" in ref_job_cancel

    # /api/files/upload path response (POST)
    file_upload = schema["paths"]["/api/files/upload"]["post"]["responses"]["200"]
    assert "schema" in file_upload["content"]["application/json"]
    ref_file_upload = file_upload["content"]["application/json"]["schema"]["$ref"]
    assert "FileUploadResponse" in ref_file_upload

    # OpenAPI schema schemas validation
    components = schema["components"]["schemas"]

    # 1. HealthResponse
    assert "HealthResponse" in components
    assert set(components["HealthResponse"]["required"]) == {"status", "version", "database"}

    # 2. ConfigResponse
    assert "ConfigResponse" in components
    assert set(components["ConfigResponse"]["required"]) == {"key", "value"}

    # 3. ConfigUpdateResponse
    assert "ConfigUpdateResponse" in components
    assert set(components["ConfigUpdateResponse"]["required"]) == {"status", "key", "value"}

    # 4. JobDetailResponse
    assert "JobDetailResponse" in components
    job_detail_schema = components["JobDetailResponse"]
    assert set(job_detail_schema["required"]) >= {"id", "status"}
    assert job_detail_schema["properties"]["id"]["type"] == "string"
    assert job_detail_schema["properties"]["status"]["type"] == "string"
    assert "job_id" not in job_detail_schema["properties"]

    # 5. JobEnvelopeResponse
    assert "JobEnvelopeResponse" in components
    assert set(components["JobEnvelopeResponse"]["required"]) == {"status", "job"}
    assert components["JobEnvelopeResponse"]["properties"]["job"]["$ref"] == "#/components/schemas/JobDetailResponse"

    # 6. JobsListResponse
    assert "JobsListResponse" in components
    assert set(components["JobsListResponse"]["required"]) == {"jobs"}
    assert components["JobsListResponse"]["properties"]["jobs"]["items"]["$ref"] == "#/components/schemas/JobDetailResponse"

    # 7. CancelJobResponse
    assert "CancelJobResponse" in components
    assert set(components["CancelJobResponse"]["required"]) == {"status", "message", "job"}
    assert components["CancelJobResponse"]["properties"]["job"]["$ref"] == "#/components/schemas/JobDetailResponse"

    # 8. FileUploadResponse
    assert "FileUploadResponse" in components
    assert set(components["FileUploadResponse"]["required"]) == {"status", "message", "job"}
    assert components["FileUploadResponse"]["properties"]["job"]["$ref"] == "#/components/schemas/JobDetailResponse"
