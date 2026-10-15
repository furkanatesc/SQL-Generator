import os
import shutil
import uuid
from typing import Dict, Iterable, Optional, Tuple

from app.settings import get_settings
from app.database import get_config, get_db_connection, get_db_path
from app.api.schemas import ComponentCheck, HealthResponse, RuntimeConfigDiagnostics
from app.secret_resolver import resolve_secret
from app.startup_validation import validate_runtime_config

def build_config_diagnostics() -> RuntimeConfigDiagnostics:
    """Runtime config diagnostics, shared by the health response and the
    /api/v1/admin/config endpoint (so admin need not build a full HealthResponse)."""
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

    return RuntimeConfigDiagnostics(
        environment=settings.environment,
        debug_endpoints_enabled=settings.debug_endpoints_enabled,
        cors_origins_count=len(settings.cors_allow_origins),
        upload_dir_configured=upload_dir_configured,
        api_key_configured=api_key_configured,
        startup_warnings_count=warnings_count,
        startup_critical_warnings_count=critical_warnings_count,
    )


def build_health_response() -> HealthResponse:
    settings = get_settings()
    return HealthResponse(
        status="ok",
        version=settings.app_version,
        database="SQLite ready",
        config=build_config_diagnostics(),
    )


# --- Sprint 32.7: per-component readiness checks ------------------------------------------------

COMPONENTS = (
    "database", "migrations", "api_key", "secrets", "upload_dir", "job_queue", "disk", "llm", "config",
)

# Startup-validation code -> component. Anything unmapped belongs to "config".
WARNING_COMPONENT = {
    "DB_MIGRATIONS_PENDING": "migrations",
    "DB_SCHEMA_AHEAD": "migrations",
    "API_KEY_NOT_CONFIGURED": "api_key",
    "API_KEY_INSECURE_DEFAULT": "api_key",
    "API_KEY_ENV_SHADOWED": "api_key",
    "SECRET_FILE_UNREADABLE": "secrets",
    "SECRET_SOURCE_CONFLICT": "secrets",
    "UPLOAD_DIR_NOT_WRITABLE": "upload_dir",
    "UPLOAD_DIR_NOT_FOUND": "upload_dir",
    "JOB_QUEUE_STALLED": "job_queue",
}

_RANK = {"ok": 0, "degraded": 1, "fail": 2}


def _merge(checks: Dict[str, ComponentCheck], name: str, status: str, reason: Optional[str]) -> None:
    if _RANK[status] > _RANK[checks[name].status]:
        checks[name] = ComponentCheck(status=status, reason=reason)


def _disk_check(min_free_mb: int) -> Tuple[str, Optional[str]]:
    if min_free_mb <= 0:
        return "ok", "disabled"
    try:
        directory = os.path.dirname(os.path.abspath(get_db_path())) or "."
        free_mb = shutil.disk_usage(directory).free / (1024 * 1024)
    except Exception:
        return "degraded", "disk_usage_unavailable"
    if free_mb < min_free_mb:
        return "fail", "low_disk_space"
    if free_mb < 2 * min_free_mb:
        return "degraded", "disk_space_low_soon"
    return "ok", None


def _llm_key_configured() -> bool:
    try:
        return bool(resolve_secret("NVIDIA_API_KEY") or get_config("nvidia_api_key"))
    except Exception:
        return False


def build_component_checks(warnings: Iterable, database_reachable: bool) -> Dict[str, ComponentCheck]:
    """Fixed component names and short reason codes only: /ready is unauthenticated."""
    checks = {name: ComponentCheck(status="ok", reason=None) for name in COMPONENTS}
    if not database_reachable:
        _merge(checks, "database", "fail", "unreachable")
    for w in warnings:
        component = WARNING_COMPONENT.get(w.code, "config")
        _merge(checks, component, "fail" if w.severity == "critical" else "degraded", w.code.lower())
    status, reason = _disk_check(get_settings().health_min_free_disk_mb)
    if status != "ok" or reason:
        checks["disk"] = ComponentCheck(status=status, reason=reason)
    if not _llm_key_configured():
        _merge(checks, "llm", "degraded", "llm_key_not_configured")
    return checks


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
        warnings = list(validation_res.warnings)
        critical_warnings_count = sum(1 for w in warnings if w.severity == "critical")
        api_key_configured = not any(w.code == "API_KEY_NOT_CONFIGURED" for w in warnings)
        upload_dir_writable = not any(w.code in ["UPLOAD_DIR_NOT_WRITABLE", "UPLOAD_DIR_NOT_FOUND"] for w in warnings)
    except Exception:
        warnings = []
        critical_warnings_count = 1  # Fail readiness on config validation crash
        api_key_configured = False
        upload_dir_writable = False

    checks = build_component_checks(warnings, database_reachable)
    ready = (
        database_reachable
        and api_key_configured
        and upload_dir_writable
        and critical_warnings_count == 0
        and all(c.status != "fail" for c in checks.values())
    )
    return {
        "database_reachable": database_reachable,
        "api_key_configured": api_key_configured,
        "upload_dir_writable": upload_dir_writable,
        "critical_warnings_count": critical_warnings_count,
        "checks": checks,
        "ready": ready,
    }
