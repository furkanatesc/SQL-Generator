import os
from pydantic import BaseModel
from typing import Literal
from app.settings import get_settings
from app.database import get_config

class StartupValidationWarning(BaseModel):
    code: str
    severity: Literal["info", "warning", "critical"]
    message: str

class StartupValidationResult(BaseModel):
    ok: bool
    warnings: list[StartupValidationWarning]

def is_production_like_environment(environment: str) -> bool:
    normalized = environment.strip().lower()
    return (
        normalized == "production"
        or normalized == "prod"
        or normalized.startswith("production-")
        or normalized.startswith("prod-")
    )

def validate_runtime_config() -> StartupValidationResult:
    import uuid
    settings = get_settings()
    warnings = []
    
    # 1. API key configured check
    try:
        db_api_key = get_config("api_key")
    except Exception:
        db_api_key = None
    env_api_key = os.getenv("NL2SQL_API_KEY")
    if not (db_api_key or env_api_key):
        warnings.append(StartupValidationWarning(
            code="API_KEY_NOT_CONFIGURED",
            severity="critical",
            message="API key is not configured via database config or environment fallback."
        ))
        
    # 2. CORS wildcard in production check
    is_prod = is_production_like_environment(settings.environment)
    if is_prod and "*" in settings.cors_allow_origins:
        warnings.append(StartupValidationWarning(
            code="CORS_WILDCARD_IN_PRODUCTION",
            severity="critical",
            message="Wildcard CORS origins allow * is enabled in a production environment."
        ))
        
    # 3. Debug endpoints enabled in production check
    if is_prod and settings.debug_endpoints_enabled:
        warnings.append(StartupValidationWarning(
            code="DEBUG_ENDPOINTS_ENABLED_IN_PRODUCTION",
            severity="critical",
            message="Debug endpoints are enabled in a production environment."
        ))
        
    # 4. Upload directory explicit check & writability
    upload_dir = settings.upload_dir
    if upload_dir is None:
        warnings.append(StartupValidationWarning(
            code="UPLOAD_DIR_DEFAULT",
            severity="info",
            message="Upload directory is not explicitly configured; using the default path."
        ))
        # Ensure we don't leak secrets or paths in warnings, but resolve the fallback safely internally
        upload_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")
    
    if upload_dir:
        abs_upload_dir = os.path.abspath(upload_dir)
        if os.path.exists(abs_upload_dir) and os.path.isdir(abs_upload_dir):
            temp_file_path = os.path.join(abs_upload_dir, f".ready_check_{uuid.uuid4()}")
            try:
                with open(temp_file_path, "w", encoding="utf-8") as f:
                    f.write("ready")
                os.remove(temp_file_path)
            except Exception:
                warnings.append(StartupValidationWarning(
                    code="UPLOAD_DIR_NOT_WRITABLE",
                    severity="critical",
                    message="Upload directory is not writable."
                ))
        else:
            warnings.append(StartupValidationWarning(
                code="UPLOAD_DIR_NOT_FOUND",
                severity="critical",
                message="Upload directory does not exist or is not a directory."
            ))
            
    ok = not any(w.severity == "critical" for w in warnings)
    
    return StartupValidationResult(ok=ok, warnings=warnings)
