import os
from pydantic import BaseModel
from typing import Literal
from app.settings import DEV_DEFAULT_API_KEY, get_settings, is_production_like_environment
from app.database import get_config
from app.config_contract import find_unknown_prefixed_env
from app.migrations.status import database_statuses
from app.secret_resolver import SECRET_FILE_VARS, resolve_secret, resolve_secret_detail

class StartupValidationWarning(BaseModel):
    code: str
    severity: Literal["info", "warning", "critical"]
    message: str

class StartupValidationResult(BaseModel):
    ok: bool
    warnings: list[StartupValidationWarning]

def validate_runtime_config() -> StartupValidationResult:
    import uuid
    settings = get_settings()
    warnings = []
    
    # 1. API key configured check
    try:
        db_api_key = get_config("api_key")
    except Exception:
        db_api_key = None
    env_api_key = resolve_secret("NL2SQL_API_KEY")
    if not (db_api_key or env_api_key):
        warnings.append(StartupValidationWarning(
            code="API_KEY_NOT_CONFIGURED",
            severity="critical",
            message="API key is not configured via database config or environment fallback."
        ))

    # 1a. Secret sources (Sprint 32.2). Variable names only, never values or file paths.
    for secret_name in SECRET_FILE_VARS:
        resolution = resolve_secret_detail(secret_name)
        if resolution.error:
            warnings.append(StartupValidationWarning(
                code="SECRET_FILE_UNREADABLE",
                severity="critical",
                message=(
                    f"{resolution.file_var} is set but the secret file is {resolution.error}; "
                    f"{secret_name} is treated as not configured."
                )
            ))
        if resolution.conflict:
            warnings.append(StartupValidationWarning(
                code="SECRET_SOURCE_CONFLICT",
                severity="warning",
                message=(
                    f"Both {secret_name} and {resolution.file_var} are set; "
                    f"the file wins and {secret_name} is ignored."
                )
            ))

    # 1c. DB key shadows the env/file key (verify_api_key prefers the DB), so rotating the
    # env/file secret would have no effect.
    if db_api_key and env_api_key and db_api_key != env_api_key:
        warnings.append(StartupValidationWarning(
            code="API_KEY_ENV_SHADOWED",
            severity="warning",
            message=(
                "An API key stored in the database config shadows the NL2SQL_API_KEY / "
                "NL2SQL_API_KEY_FILE value; change it via the config API or remove it."
            )
        ))

    is_prod = is_production_like_environment(settings.environment)

    # 1b. Effective key (DB wins over env, as in verify_api_key) is the public dev default
    if is_prod and (db_api_key or env_api_key) == DEV_DEFAULT_API_KEY:
        warnings.append(StartupValidationWarning(
            code="API_KEY_INSECURE_DEFAULT",
            severity="critical",
            message="The active API key is the public development default in a production environment."
        ))

    # 2. CORS wildcard in production check
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
            
    # 4b. Database schema versions (Sprint 32.3). Labels and version numbers only, never paths.
    try:
        db_statuses = database_statuses()
    except Exception:
        db_statuses = []
    for db, status in db_statuses:
        if status is None:
            continue
        if status.ahead:
            warnings.append(StartupValidationWarning(
                code="DB_SCHEMA_AHEAD",
                severity="critical",
                message=(
                    f"The {db.label} database schema is at version {status.current}, newer than this "
                    f"release supports ({status.latest}); no migrations were applied."
                )
            ))
        elif status.pending:
            warnings.append(StartupValidationWarning(
                code="DB_MIGRATIONS_PENDING",
                severity="critical",
                message=(
                    f"The {db.label} database has pending migrations {status.pending} "
                    f"(at version {status.current} of {status.latest}); a migration likely failed."
                )
            ))

    # 5. Unknown NL2SQL_* variables (Sprint 32.1): Settings ignores extras, so a typo
    # would otherwise be silently dropped. Names only, never values.
    unknown_env = find_unknown_prefixed_env(os.environ)
    if unknown_env:
        warnings.append(StartupValidationWarning(
            code="UNKNOWN_CONFIG_ENV_VAR",
            severity="warning",
            message=(
                "Unrecognized configuration environment variables (possible typo): "
                + ", ".join(unknown_env)
            )
        ))

    ok = not any(w.severity == "critical" for w in warnings)
    
    return StartupValidationResult(ok=ok, warnings=warnings)
