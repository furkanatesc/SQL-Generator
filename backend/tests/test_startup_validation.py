from unittest.mock import patch
from app.settings import get_settings
from app.startup_validation import validate_runtime_config
from app.health import build_health_response

def test_startup_validation_does_not_leak_secret_values(monkeypatch):
    # Setup multiple warnings
    monkeypatch.setenv("NL2SQL_ENVIRONMENT", "production")
    monkeypatch.setenv("NL2SQL_CORS_ALLOW_ORIGINS", '["*"]')
    monkeypatch.setenv("NL2SQL_DEBUG_ENDPOINTS_ENABLED", "true")
    monkeypatch.delenv("NL2SQL_UPLOAD_DIR", raising=False)
    monkeypatch.delenv("NL2SQL_API_KEY", raising=False)
    get_settings.cache_clear()
    
    with patch("app.startup_validation.get_config", return_value=None):
        result = validate_runtime_config()
        
        # Verify warnings were generated
        assert len(result.warnings) > 0
        
        # Check that none of the warning representations expose secrets/paths
        for w in result.warnings:
            w_str = str(w).lower()
            assert "api_key" not in w.message.lower()
            assert "uploads" not in w_str
            assert ".env" not in w_str

def test_startup_validation_detects_missing_api_key(monkeypatch):
    # Scenario A: Missing API key
    monkeypatch.delenv("NL2SQL_API_KEY", raising=False)
    get_settings.cache_clear()
    
    with patch("app.startup_validation.get_config", return_value=None):
        result = validate_runtime_config()
        assert result.ok is False
        
        warnings_codes = [w.code for w in result.warnings]
        assert "API_KEY_NOT_CONFIGURED" in warnings_codes
        
        # Check severity is critical
        api_key_w = next(w for w in result.warnings if w.code == "API_KEY_NOT_CONFIGURED")
        assert api_key_w.severity == "critical"

    # Scenario B: Configured in DB
    monkeypatch.delenv("NL2SQL_API_KEY", raising=False)
    get_settings.cache_clear()
    
    with patch("app.startup_validation.get_config", return_value="db-secret-key"):
        result = validate_runtime_config()
        warnings_codes = [w.code for w in result.warnings]
        assert "API_KEY_NOT_CONFIGURED" not in warnings_codes

    # Scenario C: Configured in env fallback
    monkeypatch.setenv("NL2SQL_API_KEY", "env-secret-key")
    get_settings.cache_clear()
    
    with patch("app.startup_validation.get_config", return_value=None):
        result = validate_runtime_config()
        warnings_codes = [w.code for w in result.warnings]
        assert "API_KEY_NOT_CONFIGURED" not in warnings_codes

def test_startup_validation_rejects_wildcard_cors_in_production(monkeypatch):
    # Scenario A: Production + Wildcard CORS
    monkeypatch.setenv("NL2SQL_ENVIRONMENT", "production")
    monkeypatch.setenv("NL2SQL_CORS_ALLOW_ORIGINS", '["*"]')
    get_settings.cache_clear()
    
    with patch("app.startup_validation.get_config", return_value="some-key"):
        result = validate_runtime_config()
        warnings_codes = [w.code for w in result.warnings]
        assert "CORS_WILDCARD_IN_PRODUCTION" in warnings_codes
        cors_w = next(w for w in result.warnings if w.code == "CORS_WILDCARD_IN_PRODUCTION")
        assert cors_w.severity == "critical"

    # Scenario B: Production + Specific CORS
    monkeypatch.setenv("NL2SQL_ENVIRONMENT", "production")
    monkeypatch.setenv("NL2SQL_CORS_ALLOW_ORIGINS", '["https://myapp.com"]')
    get_settings.cache_clear()
    
    with patch("app.startup_validation.get_config", return_value="some-key"):
        result = validate_runtime_config()
        warnings_codes = [w.code for w in result.warnings]
        assert "CORS_WILDCARD_IN_PRODUCTION" not in warnings_codes

    # Scenario C: Local + Wildcard CORS
    monkeypatch.setenv("NL2SQL_ENVIRONMENT", "local")
    monkeypatch.setenv("NL2SQL_CORS_ALLOW_ORIGINS", '["*"]')
    get_settings.cache_clear()
    
    with patch("app.startup_validation.get_config", return_value="some-key"):
        result = validate_runtime_config()
        warnings_codes = [w.code for w in result.warnings]
        assert "CORS_WILDCARD_IN_PRODUCTION" not in warnings_codes

def test_startup_validation_rejects_debug_endpoints_in_production(monkeypatch):
    # Scenario A: Production + Debug Enabled
    monkeypatch.setenv("NL2SQL_ENVIRONMENT", "production")
    monkeypatch.setenv("NL2SQL_DEBUG_ENDPOINTS_ENABLED", "true")
    get_settings.cache_clear()
    
    with patch("app.startup_validation.get_config", return_value="some-key"):
        result = validate_runtime_config()
        warnings_codes = [w.code for w in result.warnings]
        assert "DEBUG_ENDPOINTS_ENABLED_IN_PRODUCTION" in warnings_codes
        debug_w = next(w for w in result.warnings if w.code == "DEBUG_ENDPOINTS_ENABLED_IN_PRODUCTION")
        assert debug_w.severity == "critical"

    # Scenario B: Production + Debug Disabled
    monkeypatch.setenv("NL2SQL_ENVIRONMENT", "production")
    monkeypatch.setenv("NL2SQL_DEBUG_ENDPOINTS_ENABLED", "false")
    get_settings.cache_clear()
    
    with patch("app.startup_validation.get_config", return_value="some-key"):
        result = validate_runtime_config()
        warnings_codes = [w.code for w in result.warnings]
        assert "DEBUG_ENDPOINTS_ENABLED_IN_PRODUCTION" not in warnings_codes

def test_upload_dir_unset_warning(monkeypatch):
    # Scenario A: Upload dir unset
    monkeypatch.delenv("NL2SQL_UPLOAD_DIR", raising=False)
    get_settings.cache_clear()
    
    with patch("app.startup_validation.get_config", return_value="some-key"):
        result = validate_runtime_config()
        warnings_codes = [w.code for w in result.warnings]
        assert "UPLOAD_DIR_DEFAULT" in warnings_codes
        upload_w = next(w for w in result.warnings if w.code == "UPLOAD_DIR_DEFAULT")
        assert upload_w.severity == "info"

    # Scenario B: Upload dir set
    monkeypatch.setenv("NL2SQL_UPLOAD_DIR", "/custom/path")
    get_settings.cache_clear()
    
    with patch("app.startup_validation.get_config", return_value="some-key"):
        result = validate_runtime_config()
        warnings_codes = [w.code for w in result.warnings]
        assert "UPLOAD_DIR_DEFAULT" not in warnings_codes

def test_health_config_includes_warning_counts(monkeypatch):
    # Setup production with CORS wildcard, debug enabled, default upload_dir, and missing API key
    monkeypatch.setenv("NL2SQL_ENVIRONMENT", "production")
    monkeypatch.setenv("NL2SQL_CORS_ALLOW_ORIGINS", '["*"]')
    monkeypatch.setenv("NL2SQL_DEBUG_ENDPOINTS_ENABLED", "true")
    monkeypatch.delenv("NL2SQL_UPLOAD_DIR", raising=False)
    monkeypatch.delenv("NL2SQL_API_KEY", raising=False)
    get_settings.cache_clear()
    
    with patch("app.startup_validation.get_config", return_value=None):
        response = build_health_response().model_dump()
        assert response["config"]["startup_warnings_count"] == 4
        # API key missing -> critical, wildcard CORS -> critical, debug enabled -> critical
        assert response["config"]["startup_critical_warnings_count"] == 3

def test_warning_counts_are_deterministic(monkeypatch):
    monkeypatch.setenv("NL2SQL_ENVIRONMENT", "production")
    monkeypatch.setenv("NL2SQL_CORS_ALLOW_ORIGINS", '["*"]')
    monkeypatch.setenv("NL2SQL_DEBUG_ENDPOINTS_ENABLED", "true")
    get_settings.cache_clear()
    
    with patch("app.startup_validation.get_config", return_value="some-key"):
        res1 = validate_runtime_config()
        res2 = validate_runtime_config()
        
        assert res1.ok == res2.ok
        assert len(res1.warnings) == len(res2.warnings)
        assert [w.code for w in res1.warnings] == [w.code for w in res2.warnings]

def test_production_like_environment_detection_scenarios(monkeypatch):
    # 1. production-eu + wildcard CORS => CORS_WILDCARD_IN_PRODUCTION
    monkeypatch.setenv("NL2SQL_ENVIRONMENT", "production-eu")
    monkeypatch.setenv("NL2SQL_CORS_ALLOW_ORIGINS", '["*"]')
    get_settings.cache_clear()
    with patch("app.startup_validation.get_config", return_value="some-key"):
        result = validate_runtime_config()
        warnings_codes = [w.code for w in result.warnings]
        assert "CORS_WILDCARD_IN_PRODUCTION" in warnings_codes

    # 2. prod-eu + debug enabled => DEBUG_ENDPOINTS_ENABLED_IN_PRODUCTION
    monkeypatch.setenv("NL2SQL_ENVIRONMENT", "prod-eu")
    monkeypatch.setenv("NL2SQL_CORS_ALLOW_ORIGINS", '["https://site.com"]')
    monkeypatch.setenv("NL2SQL_DEBUG_ENDPOINTS_ENABLED", "true")
    get_settings.cache_clear()
    with patch("app.startup_validation.get_config", return_value="some-key"):
        result = validate_runtime_config()
        warnings_codes = [w.code for w in result.warnings]
        assert "DEBUG_ENDPOINTS_ENABLED_IN_PRODUCTION" in warnings_codes

    # 3. local + wildcard CORS => no production warning
    monkeypatch.setenv("NL2SQL_ENVIRONMENT", "local")
    monkeypatch.setenv("NL2SQL_CORS_ALLOW_ORIGINS", '["*"]')
    monkeypatch.setenv("NL2SQL_DEBUG_ENDPOINTS_ENABLED", "true")
    get_settings.cache_clear()
    with patch("app.startup_validation.get_config", return_value="some-key"):
        result = validate_runtime_config()
        warnings_codes = [w.code for w in result.warnings]
        assert "CORS_WILDCARD_IN_PRODUCTION" not in warnings_codes
        assert "DEBUG_ENDPOINTS_ENABLED_IN_PRODUCTION" not in warnings_codes

    # 4. development + debug enabled => no production warning
    monkeypatch.setenv("NL2SQL_ENVIRONMENT", "development")
    monkeypatch.setenv("NL2SQL_DEBUG_ENDPOINTS_ENABLED", "true")
    monkeypatch.setenv("NL2SQL_CORS_ALLOW_ORIGINS", '["*"]')
    get_settings.cache_clear()
    with patch("app.startup_validation.get_config", return_value="some-key"):
        result = validate_runtime_config()
        warnings_codes = [w.code for w in result.warnings]
        assert "CORS_WILDCARD_IN_PRODUCTION" not in warnings_codes
        assert "DEBUG_ENDPOINTS_ENABLED_IN_PRODUCTION" not in warnings_codes
