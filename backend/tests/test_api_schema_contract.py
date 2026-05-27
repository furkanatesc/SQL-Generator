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
@patch("app.main.list_jobs", return_value=[{"id": "job-123"}, {"id": "job-456"}])
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


# 6. Verify OpenAPI schema contains response models and correct required properties
def test_openapi_has_response_models_for_public_endpoints():
    schema = client.get("/openapi.json").json()

    # /health path response
    health = schema["paths"]["/health"]["get"]["responses"]["200"]
    assert "schema" in health["content"]["application/json"]
    assert "HealthResponse" in str(health)

    # /api/configs/{key} path response (GET)
    config_get = schema["paths"]["/api/configs/{key}"]["get"]["responses"]["200"]
    assert "schema" in config_get["content"]["application/json"]
    assert "ConfigResponse" in str(config_get)

    # /api/configs/{key} path response (POST)
    config_post = schema["paths"]["/api/configs/{key}"]["post"]["responses"]["200"]
    assert "schema" in config_post["content"]["application/json"]
    assert "ConfigUpdateResponse" in str(config_post)

    # /api/jobs/without-file path response (POST)
    job_post = schema["paths"]["/api/jobs/without-file"]["post"]["responses"]["200"]
    assert "schema" in job_post["content"]["application/json"]
    assert "JobEnvelopeResponse" in str(job_post)

    # /api/jobs path response (GET)
    jobs_get = schema["paths"]["/api/jobs"]["get"]["responses"]["200"]
    assert "schema" in jobs_get["content"]["application/json"]
    assert "JobsListResponse" in str(jobs_get)

    # OpenAPI schema schemas validation
    components = schema["components"]["schemas"]
    assert "HealthResponse" in components
    assert set(components["HealthResponse"]["required"]) == {"status", "version", "database"}
