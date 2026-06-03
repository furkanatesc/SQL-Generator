import os
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.settings import get_settings
from app.health import build_health_response
from app.main import app

def test_health_response_structure_and_safe_diagnostics():
    # Ensure settings is clean
    get_settings.cache_clear()
    
    response = build_health_response().model_dump()
    
    assert response["status"] == "ok"
    assert "version" in response
    assert response["database"] == "SQLite ready"
    
    # Assert config structure
    assert "config" in response
    config = response["config"]
    assert "environment" in config
    assert "debug_endpoints_enabled" in config
    assert "cors_origins_count" in config
    assert "upload_dir_configured" in config
    assert "api_key_configured" in config
    
    # Assert no secrets are exposed in values or keys
    response_str = str(response).lower()
    assert "api_key" not in config
    assert "uploads" not in response_str
    assert "sqlgen.db" not in response_str

def test_health_uses_app_version(monkeypatch):
    monkeypatch.setenv("NL2SQL_APP_VERSION", "12.3.4")
    get_settings.cache_clear()
    
    response = build_health_response().model_dump()
    assert response["version"] == "12.3.4"

def test_health_api_key_configured_scenarios(monkeypatch):
    # Scenario A: DB API key exists, env API key does not
    monkeypatch.delenv("NL2SQL_API_KEY", raising=False)
    get_settings.cache_clear()
    
    with patch("app.health.get_config", return_value="my-secret-db-key"):
        response = build_health_response().model_dump()
        assert response["config"]["api_key_configured"] is True
        # Verify secret value not leaked
        response_str = str(response)
        assert "my-secret-db-key" not in response_str

    # Scenario B: DB API key does not exist, env API key exists
    monkeypatch.setenv("NL2SQL_API_KEY", "my-secret-env-key")
    get_settings.cache_clear()
    
    with patch("app.health.get_config", return_value=None):
        response = build_health_response().model_dump()
        assert response["config"]["api_key_configured"] is True
        # Verify secret value not leaked
        response_str = str(response)
        assert "my-secret-env-key" not in response_str

    # Scenario C: Neither exists
    monkeypatch.delenv("NL2SQL_API_KEY", raising=False)
    get_settings.cache_clear()
    
    with patch("app.health.get_config", return_value=None):
        response = build_health_response().model_dump()
        assert response["config"]["api_key_configured"] is False

def test_health_upload_dir_configured_scenarios(monkeypatch):
    # Scenario A: Default (unset)
    monkeypatch.delenv("NL2SQL_UPLOAD_DIR", raising=False)
    get_settings.cache_clear()
    
    response = build_health_response().model_dump()
    assert response["config"]["upload_dir_configured"] is False

    # Scenario B: Override provided
    custom_path = "/var/lib/sqlgen/custom_uploads"
    monkeypatch.setenv("NL2SQL_UPLOAD_DIR", custom_path)
    get_settings.cache_clear()
    
    response = build_health_response().model_dump()
    assert response["config"]["upload_dir_configured"] is True
    # Verify exact path not leaked
    response_str = str(response)
    assert custom_path not in response_str

def test_health_cors_origins_count(monkeypatch):
    # Set custom origins
    monkeypatch.setenv("NL2SQL_CORS_ALLOW_ORIGINS", '["https://site-a.com", "https://site-b.com", "https://site-c.com"]')
    get_settings.cache_clear()
    
    response = build_health_response().model_dump()
    assert response["config"]["cors_origins_count"] == 3
    
    # Verify no raw origins leaked
    response_str = str(response)
    assert "site-a.com" not in response_str

def test_health_environment_from_settings(monkeypatch):
    monkeypatch.setenv("NL2SQL_ENVIRONMENT", "production-eu")
    get_settings.cache_clear()
    
    response = build_health_response().model_dump()
    assert response["config"]["environment"] == "production-eu"

def test_health_endpoint_integration():
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "ok"
    assert "config" in data
    assert "environment" in data["config"]
    assert "cors_origins_count" in data["config"]
    
    # Verify schema mapping does not fail
    # (FastAPI automatically validates it matches HealthResponse Pydantic model)
