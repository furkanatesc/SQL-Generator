"""Metrics contract debug router (Sprint 27.6).

debug_traces.py deseni: kendi APIRouter'i, main.py'de mount edilir,
debug_endpoints_enabled kapaliyken 404 doner. Hesaplama YAN ETKISIZDIR.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.schemas import MetricsEnvelopeResponse
from app.auth import verify_api_key
from app.metrics_service import compute_metrics_for_window
from app.settings import get_settings
from app.trace.dependencies import get_trace_store
from app.trace.store import TraceStore

router = APIRouter(
    prefix="/api/debug/metrics",
    tags=["debug-metrics"],
    dependencies=[Depends(verify_api_key)],
)


def ensure_debug_enabled():
    if not get_settings().debug_endpoints_enabled:
        raise HTTPException(status_code=404, detail="Not found")


@router.get("", response_model=MetricsEnvelopeResponse)
def metrics(
    created_after: Optional[str] = Query(default=None),
    created_before: Optional[str] = Query(default=None),
    dialect: Optional[str] = Query(default=None),
    store: TraceStore = Depends(get_trace_store),
):
    ensure_debug_enabled()
    payload = compute_metrics_for_window(
        trace_store=store, created_after=created_after,
        created_before=created_before, dialect=dialect)
    return {"status": "success", "metrics": payload}
