import os
import pytest
from fastapi.testclient import TestClient
from fastapi.middleware.cors import CORSMiddleware
from app.settings import get_settings
from app.main import app, UPLOAD_DIR

def test_fastapi_metadata_linked_to_settings():
    settings = get_settings()
    assert app.title == settings.app_name
    assert app.version == settings.app_version
    assert app.description == settings.app_description

def test_cors_middleware_linked_to_settings():
    settings = get_settings()
    cors_mw = None
    for mw in app.user_middleware:
        if mw.cls == CORSMiddleware:
            cors_mw = mw
            break
            
    assert cors_mw is not None
    assert cors_mw.kwargs["allow_origins"] == settings.cors_allow_origins
    assert cors_mw.kwargs["allow_credentials"] == settings.cors_allow_credentials
    assert cors_mw.kwargs["allow_methods"] == settings.cors_allow_methods
    assert cors_mw.kwargs["allow_headers"] == settings.cors_allow_headers

def test_upload_dir_linked_to_settings():
    settings = get_settings()
    if settings.upload_dir:
        expected = os.path.abspath(settings.upload_dir)
    else:
        # Resolve to backend/uploads relative to app.main (__file__)
        expected = os.path.abspath(os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "uploads"
        ))
    assert UPLOAD_DIR == expected
    assert os.path.exists(UPLOAD_DIR)

def test_debug_endpoint_flag_behavior(monkeypatch):
    monkeypatch.setenv("NL2SQL_API_KEY", "integration-test-key")
    client = TestClient(app)
    headers = {"X-API-Key": "integration-test-key"}
    
    from unittest.mock import patch
    with patch("app.auth.get_config", return_value=None):
        # 1. Test when debug is disabled
        monkeypatch.setenv("NL2SQL_DEBUG_ENDPOINTS_ENABLED", "false")
        get_settings.cache_clear()
        
        response = client.get("/api/debug/traces", headers=headers)
        assert response.status_code == 404
        
        # 2. Test when debug is enabled
        monkeypatch.setenv("NL2SQL_DEBUG_ENDPOINTS_ENABLED", "true")
        get_settings.cache_clear()
        
        response = client.get("/api/debug/traces", headers=headers)
        # Should bypass ensure_debug_enabled check (returns list 200)
        assert response.status_code == 200

        # 3. Test when debug is unset (defaults to True/enabled)
        monkeypatch.delenv("NL2SQL_DEBUG_ENDPOINTS_ENABLED", raising=False)
        get_settings.cache_clear()
        
        response = client.get("/api/debug/traces", headers=headers)
        assert response.status_code == 200
