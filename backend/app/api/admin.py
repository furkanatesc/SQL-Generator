"""Admin API (Sprint 30.7).

/api/v1/admin — read-only operator surface on the 30.0 contract: a runtime
overview (environment + version + Phase 11 resource counts) and the runtime
config diagnostics (reused from the health module). Protected by verify_api_key.
No writes / destructive operations.
"""
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.api.contract import API_V1_PREFIX, ApiResponse
from app.api.schemas import RuntimeConfigDiagnostics
from app.auth import verify_api_key
from app.settings import get_settings
from app.health import build_health_response
from app import admin_repository as repo

router = APIRouter(
    prefix=f"{API_V1_PREFIX}/admin",
    tags=["admin"],
    dependencies=[Depends(verify_api_key)],
)


class ResourceCounts(BaseModel):
    workspaces: int
    connections: int
    schema_syncs: int
    query_runs: int
    query_run_feedback: int


class AdminOverview(BaseModel):
    environment: str
    debug_endpoints_enabled: bool
    app_version: str
    resources: ResourceCounts


@router.get("/overview", response_model=ApiResponse[AdminOverview])
def admin_overview() -> ApiResponse[AdminOverview]:
    settings = get_settings()
    counts = repo.resource_counts()
    overview = AdminOverview(
        environment=settings.environment,
        debug_endpoints_enabled=settings.debug_endpoints_enabled,
        app_version=settings.app_version,
        resources=ResourceCounts(**counts),
    )
    return ApiResponse[AdminOverview](data=overview)


@router.get("/config", response_model=ApiResponse[RuntimeConfigDiagnostics])
def admin_config() -> ApiResponse[RuntimeConfigDiagnostics]:
    return ApiResponse[RuntimeConfigDiagnostics](data=build_health_response().config)
