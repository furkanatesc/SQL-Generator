import os
import uuid
from app.settings import get_settings
from app.database import get_config, get_db_connection
from app.api.schemas import HealthResponse, RuntimeConfigDiagnostics
from app.startup_validation import validate_runtime_config

def build_health_response() -> HealthResponse:
    settings = get_settings()
    
    # Run startup validation to count warnings and extract flags
    try:
        validation_res = validate_runtime_config()
        warnings_count = len(validation_res.warnings)
        critical_warnings_count = sum(1 for w in validation_res.warnings if w.severity == "critical")
        api_key_configured = not any(w.code == "API_KEY_NOT_CONFIGURED" for w in validation_res.warnings)
        upload_dir_configured = settings.upload_dir is not None
    except Exception:
        warnings_count = 0
        critical_warnings_count = 1
        api_key_configured = False
        upload_dir_configured = False
        
    cors_origins_count = len(settings.cors_allow_origins)
    
    config_diagnostics = RuntimeConfigDiagnostics(
        environment=settings.environment,
        debug_endpoints_enabled=settings.debug_endpoints_enabled,
        cors_origins_count=cors_origins_count,
        upload_dir_configured=upload_dir_configured,
        api_key_configured=api_key_configured,
        startup_warnings_count=warnings_count,
        startup_critical_warnings_count=critical_warnings_count,
    )
    
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        database="SQLite ready",
        config=config_diagnostics,
    )

def check_readiness() -> dict:
    # 1. Database Reachability (active SELECT 1 connectivity check)
    database_reachable = False
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            database_reachable = True
    except Exception:
        database_reachable = False
        
    # 2. Dynamic configuration validation check (Centralized)
    try:
        validation_res = validate_runtime_config()
        critical_warnings_count = sum(1 for w in validation_res.warnings if w.severity == "critical")
        api_key_configured = not any(w.code == "API_KEY_NOT_CONFIGURED" for w in validation_res.warnings)
        upload_dir_writable = not any(w.code in ["UPLOAD_DIR_NOT_WRITABLE", "UPLOAD_DIR_NOT_FOUND"] for w in validation_res.warnings)
    except Exception:
        critical_warnings_count = 1  # Fail readiness on config validation crash
        api_key_configured = False
        upload_dir_writable = False
        
    return {
        "database_reachable": database_reachable,
        "api_key_configured": api_key_configured,
        "upload_dir_writable": upload_dir_writable,
        "critical_warnings_count": critical_warnings_count
    }
