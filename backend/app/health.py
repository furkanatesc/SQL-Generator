import os
from app.settings import get_settings
from app.database import get_config
from app.api.schemas import HealthResponse, RuntimeConfigDiagnostics

def build_health_response() -> HealthResponse:
    settings = get_settings()
    
    # Check if API key is configured (either in the DB configs or in the environment)
    db_api_key = get_config("api_key")
    env_api_key = os.getenv("NL2SQL_API_KEY")
    api_key_configured = bool(db_api_key or env_api_key)
    
    # Check if upload directory is explicitly configured (not None)
    upload_dir_configured = settings.upload_dir is not None
    
    # Count the CORS origins configured
    cors_origins_count = len(settings.cors_allow_origins)
    
    config_diagnostics = RuntimeConfigDiagnostics(
        environment=settings.environment,
        debug_endpoints_enabled=settings.debug_endpoints_enabled,
        cors_origins_count=cors_origins_count,
        upload_dir_configured=upload_dir_configured,
        api_key_configured=api_key_configured,
    )
    
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        database="SQLite ready",
        config=config_diagnostics,
    )
