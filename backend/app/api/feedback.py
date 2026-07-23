"""Feedback capture router (Sprint 27.3).

api/debug_traces.py deseni: kendi APIRouter'ı, main.py'de mount edilir.
Akış: Pydantic + cross-field invariant (422) → get_job yok ise 404 →
create_feedback (append-only) → 200 envelope.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException

from app.auth import verify_api_key
from app.database import create_feedback, get_job
from app.api.schemas import (
    ErrorResponse,
    FeedbackEnvelopeResponse,
    FeedbackSubmitRequest,
)

router = APIRouter(
    prefix="/api/jobs",
    tags=["feedback"],
    dependencies=[Depends(verify_api_key)],
)


@router.post(
    "/{job_id}/feedback",
    response_model=FeedbackEnvelopeResponse,
    responses={404: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def submit_feedback(job_id: str, payload: FeedbackSubmitRequest):
    if get_job(job_id) is None:
        raise HTTPException(
            status_code=404, detail=f"Job with ID '{job_id}' not found."
        )
    feedback = create_feedback(
        feedback_id=str(uuid.uuid4()),
        job_id=job_id,
        # Sınırda PLAIN STRING taşınır (enum değil) — 27.2.1 error_code deseni.
        verdict=payload.verdict.value,
        category=payload.category.value if payload.category is not None else None,
        note=payload.note,
        corrected_sql=payload.corrected_sql,
    )
    return {"status": "success", "feedback": feedback}
