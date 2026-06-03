import os
import sys
import importlib
import pytest
from fastapi.testclient import TestClient
from fastapi.middleware.cors import CORSMiddleware
from app.settings import get_settings

@pytest.fixture(autouse=True, scope="module")
def cleanup_after_module():
    yield
    # Restore the default environment settings for the test session
    os.environ["NL2SQL_DEBUG_ENDPOINTS_ENABLED"] = "true"
    get_settings.cache_clear()
    if "app.main" in sys.modules:
        importlib.reload(sys.modules["app.main"])

def test_fastapi_metadata_default(monkeypatch):
    # Clear environment variables with NL2SQL_ prefix
    for key in list(os.environ.keys()):
        if key.startswith("NL2SQL_"):
            monkeypatch.delenv(key, raising=False)
            
    get_settings.cache_clear()
    if "app.main" in sys.modules:
        importlib.reload(sys.modules["app.main"])
    import app.main
    
    assert app.main.app.title == "SQLGen API"
    assert app.main.app.version == "0.1.0"
    assert app.main.app.description == "SQLGen platformu için lokal FastAPI API katmanı"

def test_fastapi_metadata_override(monkeypatch):
    monkeypatch.setenv("NL2SQL_APP_NAME", "Override Title")
    monkeypatch.setenv("NL2SQL_APP_VERSION", "9.9.9")
    monkeypatch.setenv("NL2SQL_APP_DESCRIPTION", "Override Desc")
    
    get_settings.cache_clear()
    if "app.main" in sys.modules:
        importlib.reload(sys.modules["app.main"])
    import app.main
    
    assert app.main.app.title == "Override Title"
    assert app.main.app.version == "9.9.9"
    assert app.main.app.description == "Override Desc"

def test_cors_middleware_default(monkeypatch):
    for key in list(os.environ.keys()):
        if key.startswith("NL2SQL_"):
            monkeypatch.delenv(key, raising=False)
            
    get_settings.cache_clear()
    if "app.main" in sys.modules:
        importlib.reload(sys.modules["app.main"])
    import app.main
    
    cors_mw = None
    for mw in app.main.app.user_middleware:
        if mw.cls == CORSMiddleware:
            cors_mw = mw
            break
            
    assert cors_mw is not None
    assert cors_mw.kwargs["allow_origins"] == ["*"]
    assert cors_mw.kwargs["allow_credentials"] is True
    assert cors_mw.kwargs["allow_methods"] == ["*"]
    assert cors_mw.kwargs["allow_headers"] == ["*"]

def test_cors_middleware_override(monkeypatch):
    monkeypatch.setenv("NL2SQL_CORS_ALLOW_ORIGINS", '["https://example.com"]')
    monkeypatch.setenv("NL2SQL_CORS_ALLOW_CREDENTIALS", "false")
    monkeypatch.setenv("NL2SQL_CORS_ALLOW_METHODS", '["GET", "POST"]')
    monkeypatch.setenv("NL2SQL_CORS_ALLOW_HEADERS", '["X-Custom"]')
    
    get_settings.cache_clear()
    if "app.main" in sys.modules:
        importlib.reload(sys.modules["app.main"])
    import app.main
    
    cors_mw = None
    for mw in app.main.app.user_middleware:
        if mw.cls == CORSMiddleware:
            cors_mw = mw
            break
            
    assert cors_mw is not None
    assert cors_mw.kwargs["allow_origins"] == ["https://example.com"]
    assert cors_mw.kwargs["allow_credentials"] is False
    assert cors_mw.kwargs["allow_methods"] == ["GET", "POST"]
    assert cors_mw.kwargs["allow_headers"] == ["X-Custom"]

def test_upload_dir_default(monkeypatch):
    monkeypatch.delenv("NL2SQL_UPLOAD_DIR", raising=False)
    
    get_settings.cache_clear()
    if "app.main" in sys.modules:
        importlib.reload(sys.modules["app.main"])
    import app.main
    
    expected_default = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(app.main.__file__))),
        "uploads"
    )
    assert app.main.UPLOAD_DIR == expected_default
    assert os.path.exists(app.main.UPLOAD_DIR)

def test_upload_dir_override(monkeypatch, tmp_path):
    custom_dir = tmp_path / "custom_uploads"
    monkeypatch.setenv("NL2SQL_UPLOAD_DIR", str(custom_dir))
    
    get_settings.cache_clear()
    if "app.main" in sys.modules:
        importlib.reload(sys.modules["app.main"])
    import app.main
    
    assert app.main.UPLOAD_DIR == os.path.abspath(str(custom_dir))
    assert os.path.exists(app.main.UPLOAD_DIR)

def test_debug_endpoint_flag_behavior(monkeypatch):
    monkeypatch.setenv("NL2SQL_API_KEY", "integration-test-key")
    
    get_settings.cache_clear()
    if "app.main" in sys.modules:
        importlib.reload(sys.modules["app.main"])
    import app.main
    
    client = TestClient(app.main.app)
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
        # Should bypass ensure_debug_enabled check (even if empty, returns list 200)
        assert response.status_code == 200
