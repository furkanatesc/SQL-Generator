import os
import sqlite3
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app
from app.settings import get_settings
from app.auth import verify_api_key

client = TestClient(app)

def test_health_remains_liveness():
    response = client.get("/health")
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert data["database"] == "SQLite ready"
    assert "config" in data
    assert isinstance(data["config"]["startup_warnings_count"], int)
    assert isinstance(data["config"]["startup_critical_warnings_count"], int)

def test_readiness_healthy_environment():
    get_settings.cache_clear()
    response = client.get("/ready")
    assert response.status_code == 200
    
    data = response.json()
    assert data["status"] == "ok"
    assert data["database_reachable"] is True
    assert data["api_key_configured"] is True
    assert data["upload_dir_writable"] is True
    assert data["critical_warnings_count"] == 0

def test_readiness_db_offline(monkeypatch):
    # Mock get_db_connection to throw an operational exception
    def mock_db_conn():
        raise sqlite3.OperationalError("Database locked or unreachable")
        
    monkeypatch.setattr("app.health.get_db_connection", mock_db_conn)
    
    response = client.get("/ready")
    assert response.status_code == 503
    
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["database_reachable"] is False

def test_readiness_api_key_unconfigured(monkeypatch):
    monkeypatch.delenv("NL2SQL_API_KEY", raising=False)
    get_settings.cache_clear()
    
    with patch("app.health.get_config", return_value=None):
        response = client.get("/ready")
        assert response.status_code == 503
        
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["api_key_configured"] is False

def test_readiness_upload_dir_not_writable(monkeypatch):
    # Force settings.upload_dir to an invalid, unwritable path
    monkeypatch.setenv("NL2SQL_UPLOAD_DIR", "/invalid/unwritable/uploads/dir/12345")
    get_settings.cache_clear()
    
    response = client.get("/ready")
    assert response.status_code == 503
    
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["upload_dir_writable"] is False

def test_readiness_unhealthy_when_startup_validation_has_critical_warning(monkeypatch):
    # Mock validate_runtime_config to return a critical warning
    class MockWarning:
        def __init__(self):
            self.severity = "critical"
            self.code = "SOME_CRITICAL_WARNING"
            
    class MockResult:
        def __init__(self):
            self.warnings = [MockWarning()]
            
    monkeypatch.setattr("app.health.validate_runtime_config", lambda: MockResult())
    
    response = client.get("/ready")
    assert response.status_code == 503
    
    data = response.json()
    assert data["status"] == "unhealthy"
    assert data["critical_warnings_count"] == 1

def test_readiness_no_secret_leak():
    response = client.get("/ready")
    assert response.status_code == 200
    
    body_str = str(response.json()).lower()
    
    # Assert no secret path, filename, or credentials leak in the response structure
    assert "uploads" not in body_str
    assert "sqlgen.db" not in body_str
    assert "api_key" not in body_str or "api_key_configured" in body_str

def test_readiness_db_config_lookup_failure_returns_503(monkeypatch):
    monkeypatch.setattr("app.health.get_config", lambda key: (_ for _ in ()).throw(Exception("db down")))
    response = client.get("/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "unhealthy"
