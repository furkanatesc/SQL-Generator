"""Debug bundle export router (Sprint 27.5).

debug_replay.py deseni: kendi APIRouter'i, main.py'de mount edilir,
debug_endpoints_enabled kapaliyken 404 doner. Export YAN ETKISIZDIR.
"""
from fastapi import APIRouter, Depends, HTTPException

from app.api.schemas import BundleEnvelopeResponse, ErrorResponse
from app.auth import verify_api_key
from app.bundle_service import BundleJobNotFound, build_bundle
from app.settings import get_settings
from app.trace.dependencies import get_trace_store
from app.trace.store import TraceStore

router = APIRouter(
    prefix="/api/debug/jobs",
    tags=["debug-bundle"],
    dependencies=[Depends(verify_api_key)],
)


def ensure_debug_enabled():
    if not get_settings().debug_endpoints_enabled:
        raise HTTPException(status_code=404, detail="Not found")


def get_bundle_pipeline():
    # Lazy: debug kapaliyken agir SchemaManager insasi yapilmasin.
    from app.sql_pipeline import SQLGenerationPipeline

    return SQLGenerationPipeline(trace_store=get_trace_store())


@router.get(
    "/{job_id}/bundle",
    response_model=BundleEnvelopeResponse,
    responses={404: {"model": ErrorResponse}},
)
def bundle(
    job_id: str,
    store: TraceStore = Depends(get_trace_store),
):
    ensure_debug_enabled()
    pipeline = get_bundle_pipeline()
    try:
        payload = build_bundle(job_id, trace_store=store, pipeline=pipeline)
    except BundleJobNotFound:
        raise HTTPException(
            status_code=404, detail=f"Job with ID '{job_id}' not found.")
    return {"status": "success", "bundle": payload}
