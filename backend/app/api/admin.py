"""Admin API (Sprint 30.7).

/api/v1/admin — read-only operator surface on the 30.0 contract: a runtime
overview (environment + version + Phase 11 resource counts) and the runtime
config diagnostics (reused from the health module). Protected by verify_api_key.

Sprint 32.5 adds the job-queue view (`GET /queue`) and the only write on this surface,
`POST /jobs/{job_id}/requeue` (failed -> pending; non-destructive).
"""
from typing import Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.api.contract import API_V1_PREFIX, ApiResponse
from app.api.schemas import RuntimeConfigDiagnostics
from app.auth import verify_api_key
from app.settings import get_settings
from app.health import build_config_diagnostics
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
    return ApiResponse[RuntimeConfigDiagnostics](data=build_config_diagnostics())


class QueueStats(BaseModel):
    execution_mode: str
    counts: Dict[str, int]
    retry_scheduled: int
    dead_lettered: int
    oldest_pending_age_seconds: Optional[float] = None
    max_attempts: int
    max_concurrent: int
    retry_backoff_seconds: float


class RequeuedJob(BaseModel):
    id: str
    status: str
    attempts: int
    priority: int


@router.get("/queue", response_model=ApiResponse[QueueStats])
def admin_queue() -> ApiResponse[QueueStats]:
    from app.jobs.repository import queue_stats

    settings = get_settings()
    stats = QueueStats(
        execution_mode=settings.job_execution_mode,
        max_attempts=settings.job_max_attempts,
        max_concurrent=settings.job_max_concurrent,
        retry_backoff_seconds=settings.job_retry_backoff_seconds,
        **queue_stats(),
    )
    return ApiResponse[QueueStats](data=stats)


@router.post("/jobs/{job_id}/requeue", response_model=ApiResponse[RequeuedJob])
def admin_requeue_job(job_id: str) -> ApiResponse[RequeuedJob]:
    from app.database import get_job
    from app.jobs.repository import requeue_job

    outcome = requeue_job(job_id)
    if outcome is None:
        raise HTTPException(status_code=404, detail=f"Job with ID '{job_id}' not found.")
    if outcome is False:
        raise HTTPException(status_code=409, detail="Only failed jobs can be requeued.")
    job = get_job(job_id)
    return ApiResponse[RequeuedJob](data=RequeuedJob(
        id=job["id"], status=job["status"], attempts=job["attempts"], priority=job["priority"],
    ))
