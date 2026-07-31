"""LLM usage/cost telemetri router (Sprint 27.8).

metrics_api/dashboard_api deseni: kendi APIRouter'i, main.py'de mount edilir,
debug_endpoints_enabled kapaliyken 404 doner. Hesaplama YAN ETKISIZDIR.
"""
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.schemas import LLMUsageEnvelopeResponse
from app.auth import verify_api_key
from app.llm_usage_service import build_llm_usage
from app.settings import get_settings
from app.trace.dependencies import get_trace_store
from app.trace.store import TraceStore

router = APIRouter(
    prefix="/api/debug/llm-usage",
    tags=["debug-llm-usage"],
    dependencies=[Depends(verify_api_key)],
)


def ensure_debug_enabled():
    if not get_settings().debug_endpoints_enabled:
        raise HTTPException(status_code=404, detail="Not found")


@router.get("", response_model=LLMUsageEnvelopeResponse)
def llm_usage(
    created_after: Optional[str] = Query(default=None),
    created_before: Optional[str] = Query(default=None),
    bucket: Literal["hour", "day"] = Query(default="day"),
    store: TraceStore = Depends(get_trace_store),
):
    ensure_debug_enabled()
    payload = build_llm_usage(
        trace_store=store, created_after=created_after,
        created_before=created_before, bucket=bucket)
    return {"status": "success", "usage": payload}
