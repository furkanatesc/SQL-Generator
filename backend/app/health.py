import os
import uuid
from app.settings import get_settings
from app.database import get_config, get_db_connection
from app.api.schemas import HealthResponse, RuntimeConfigDiagnostics
from app.startup_validation import validate_runtime_config

def build_health_response() -> HealthResponse:
    settings = get_settings()
    
    # Lightweight check: DB API key check (we keep this for test compat, but avoid the startup scan)
    db_api_key = get_config("api_key")
    env_api_key = os.getenv("NL2SQL_API_KEY")
    api_key_configured = bool(db_api_key or env_api_key)
    
    # Check if upload directory is explicitly configured (not None)
    upload_dir_configured = settings.upload_dir is not None
    
    # Count the CORS origins configured
    cors_origins_count = len(settings.cors_allow_origins)
    
    # Run startup validation to count warnings
    try:
        validation_res = validate_runtime_config()
        warnings_count = len(validation_res.warnings)
        critical_warnings_count = sum(1 for w in validation_res.warnings if w.severity == "critical")
    except Exception:
        warnings_count = 0
        critical_warnings_count = 0
        
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
    settings = get_settings()
    
    # 1. Database Reachability (active SELECT 1 connectivity check)
    database_reachable = False
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            database_reachable = True
    except Exception:
        database_reachable = False
        
    # 2. API Key Configuration Check (wrapped in try/except to prevent 500 error if DB is down)
    try:
        db_api_key = get_config("api_key")
    except Exception:
        db_api_key = None
    env_api_key = os.getenv("NL2SQL_API_KEY")
    api_key_configured = bool(db_api_key or env_api_key)
    
    # 3. Upload Directory Writability Check (dynamic write/delete validation using unique UUID file name)
    upload_dir_writable = False
    if settings.upload_dir:
        upload_dir = os.path.abspath(settings.upload_dir)
    else:
        upload_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")
        
    if os.path.exists(upload_dir) and os.path.isdir(upload_dir):
        temp_file_path = os.path.join(upload_dir, f".ready_check_{uuid.uuid4()}")
        try:
            with open(temp_file_path, "w", encoding="utf-8") as f:
                f.write("ready")
            os.remove(temp_file_path)
            upload_dir_writable = True
        except Exception:
            upload_dir_writable = False
            
    # 4. Critical Startup Warnings Count (dynamic configuration validation check)
    try:
        validation_res = validate_runtime_config()
        critical_warnings_count = sum(1 for w in validation_res.warnings if w.severity == "critical")
    except Exception:
        critical_warnings_count = 1  # Fail readiness on config validation crash
        
    return {
        "database_reachable": database_reachable,
        "api_key_configured": api_key_configured,
        "upload_dir_writable": upload_dir_writable,
        "critical_warnings_count": critical_warnings_count
    }
