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
    settings = get_settings()
    warnings = []
    
    # 1. API key configured check
    db_api_key = get_config("api_key")
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
            severity="warning",
            message="Wildcard CORS origins allow * is enabled in a production environment."
        ))
        
    # 3. Debug endpoints enabled in production check
    if is_prod and settings.debug_endpoints_enabled:
        warnings.append(StartupValidationWarning(
            code="DEBUG_ENDPOINTS_ENABLED_IN_PRODUCTION",
            severity="warning",
            message="Debug endpoints are enabled in a production environment."
        ))
        
    # 4. Upload directory explicit check
    if settings.upload_dir is None:
        warnings.append(StartupValidationWarning(
            code="UPLOAD_DIR_DEFAULT",
            severity="info",
            message="Upload directory is not explicitly configured; using the default path."
        ))
        
    ok = not any(w.severity == "critical" for w in warnings)
    
    return StartupValidationResult(ok=ok, warnings=warnings)
