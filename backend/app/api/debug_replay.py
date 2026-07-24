"""Query replay debug router (Sprint 27.4).

api/debug_traces.py deseni: kendi APIRouter'i, main.py'de mount edilir,
debug_endpoints_enabled kapaliyken 404 doner.
"""
from fastapi import APIRouter, Depends, HTTPException

from app.api.schemas import ErrorResponse, ReplayEnvelopeResponse
from app.auth import verify_api_key
from app.replay_service import ReplayJobNotFound, replay_job
from app.settings import get_settings
from app.trace.dependencies import get_trace_store
from app.trace.store import TraceStore

router = APIRouter(
    prefix="/api/debug/jobs",
    tags=["debug-replay"],
    dependencies=[Depends(verify_api_key)],
)


def ensure_debug_enabled():
    if not get_settings().debug_endpoints_enabled:
        raise HTTPException(status_code=404, detail="Not found")


def get_replay_pipeline():
    # Lazy import: modul yuklenirken agir pipeline bagimliliklarini cekmemek icin.
    from app.sql_pipeline import SQLGenerationPipeline

    return SQLGenerationPipeline(trace_store=get_trace_store())


@router.post(
    "/{job_id}/replay",
    response_model=ReplayEnvelopeResponse,
    responses={404: {"model": ErrorResponse}},
)
def replay(
    job_id: str,
    store: TraceStore = Depends(get_trace_store),
):
    ensure_debug_enabled()
    # Pipeline Depends ILE DEGIL burada kurulur: debug kapaliyken (404) agir
    # SchemaManager insasi hic yapilmasin, testler de kolayca patch'leyebilsin.
    pipeline = get_replay_pipeline()
    try:
        result = replay_job(job_id, pipeline=pipeline, trace_store=store)
    except ReplayJobNotFound:
        raise HTTPException(
            status_code=404, detail=f"Job with ID '{job_id}' not found."
        )
    return {"status": "success", "replay": result.to_payload()}
