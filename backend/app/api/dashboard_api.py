"""Admin observability dashboard router (Sprint 27.7).

metrics_api.py deseni: kendi APIRouter'i, main.py'de mount edilir,
debug_endpoints_enabled kapaliyken 404 doner. Hesaplama YAN ETKISIZDIR.
"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.schemas import DashboardEnvelopeResponse
from app.auth import verify_api_key
from app.dashboard_service import build_dashboard
from app.settings import get_settings
from app.trace.dependencies import get_trace_store
from app.trace.store import TraceStore

router = APIRouter(
    prefix="/api/debug/dashboard",
    tags=["debug-dashboard"],
    dependencies=[Depends(verify_api_key)],
)


def ensure_debug_enabled():
    if not get_settings().debug_endpoints_enabled:
        raise HTTPException(status_code=404, detail="Not found")


@router.get("", response_model=DashboardEnvelopeResponse,
            dependencies=[Depends(ensure_debug_enabled)])
def dashboard(
    created_after: Optional[str] = Query(default=None),
    created_before: Optional[str] = Query(default=None),
    dialect: Optional[str] = Query(default=None),
    bucket: Literal["hour", "day"] = Query(default="day"),
    top_n: int = Query(default=10, ge=1, le=100),
    recent_limit: int = Query(default=20, ge=1, le=100),
    store: TraceStore = Depends(get_trace_store),
):
    payload = build_dashboard(
        trace_store=store, created_after=created_after, created_before=created_before,
        dialect=dialect, bucket=bucket, top_n=top_n, recent_limit=recent_limit)
    return {"status": "success", "dashboard": payload}
