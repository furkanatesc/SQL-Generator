import os
import pytest
from app.settings import get_settings, Settings
from app.auth import verify_api_key
from fastapi import HTTPException

def test_default_settings_values_load(monkeypatch):
    for key in list(os.environ.keys()):
        if key.startswith("NL2SQL_"):
            monkeypatch.delenv(key, raising=False)
    settings = Settings()
    assert settings.app_name == "SQLGen API"
    assert settings.app_version == "0.1.0"
    assert settings.app_description == "SQLGen platformu için lokal FastAPI API katmanı"
    assert settings.environment == "local"
    assert settings.cors_allow_origins == ["*"]
    assert settings.cors_allow_credentials is True
    assert settings.upload_dir is None
    assert settings.debug_endpoints_enabled is True

def test_app_name_override(monkeypatch):
    monkeypatch.setenv("NL2SQL_APP_NAME", "Custom App Name")
    settings = Settings()
    assert settings.app_name == "Custom App Name"

def test_app_version_override(monkeypatch):
    monkeypatch.setenv("NL2SQL_APP_VERSION", "2.0.0")
    settings = Settings()
    assert settings.app_version == "2.0.0"

def test_cors_allow_origins_parses_list(monkeypatch):
    monkeypatch.setenv("NL2SQL_CORS_ALLOW_ORIGINS", '["http://localhost:3000", "https://sqlgen.com"]')
    settings = Settings()
    assert settings.cors_allow_origins == ["http://localhost:3000", "https://sqlgen.com"]

def test_upload_dir_override(monkeypatch):
    monkeypatch.setenv("NL2SQL_UPLOAD_DIR", "/custom/upload/dir")
    settings = Settings()
    assert settings.upload_dir == "/custom/upload/dir"

def test_debug_endpoints_enabled_parses_boolean(monkeypatch):
    # 1. enabled = true
    monkeypatch.setenv("NL2SQL_DEBUG_ENDPOINTS_ENABLED", "true")
    settings_true = Settings()
    assert settings_true.debug_endpoints_enabled is True

    # 2. enabled = false
    monkeypatch.setenv("NL2SQL_DEBUG_ENDPOINTS_ENABLED", "false")
    settings_false = Settings()
    assert settings_false.debug_endpoints_enabled is False

def test_auth_api_key_env_fallback(monkeypatch):
    monkeypatch.setenv("NL2SQL_API_KEY", "fallback-secret-key")
    
    # We patch app.auth.get_config to return None (no DB config key exists)
    from unittest.mock import patch
    with patch("app.auth.get_config", return_value=None):
        # 1. Passing matching key succeeds
        result = verify_api_key(api_key_h="fallback-secret-key")
        assert result == "fallback-secret-key"
        
        # 2. Passing invalid key raises HTTP 403
        with pytest.raises(HTTPException) as exc:
            verify_api_key(api_key_h="wrong-key")
        assert exc.value.status_code == 403
