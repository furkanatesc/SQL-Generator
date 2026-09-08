"""Feedback API (Sprint 30.6).

/api/v1/feedback — feedback attached to a 30.4 query_run (verdict + optional
category/note/corrected_sql) on the 30.0 contract. Reuses the 27.3 feedback
enums + invariants. Protected by verify_api_key. Distinct from the legacy 27.3
job-scoped feedback router (app/api/feedback.py).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from app.api.contract import API_V1_PREFIX, ApiResponse, PageMeta, ResponseMeta
from app.auth import verify_api_key
from app.feedback import FeedbackVerdict, FeedbackCategory
from app import feedback_repository as repo
from app import query_run_repository as run_repo

router = APIRouter(
    prefix=f"{API_V1_PREFIX}/feedback",
    tags=["feedback"],
    dependencies=[Depends(verify_api_key)],
)


class FeedbackCreate(BaseModel):
    query_run_id: str
    verdict: FeedbackVerdict
    category: Optional[FeedbackCategory] = None
    note: Optional[str] = Field(default=None, max_length=2000)
    corrected_sql: Optional[str] = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def _invariants(self):
        # Replicates the 27.3 FeedbackSubmitRequest invariants.
        if self.verdict == FeedbackVerdict.CORRECT:
            if self.category is not None or self.corrected_sql is not None:
                raise ValueError("verdict=correct ile category/corrected_sql verilemez")
        if self.category == FeedbackCategory.OTHER and not (self.note and self.note.strip()):
            raise ValueError("category=other için note zorunludur")
        return self


class FeedbackResponse(BaseModel):
    id: str
    query_run_id: str
    verdict: str
    category: Optional[str] = None
    note: Optional[str] = None
    corrected_sql: Optional[str] = None
    created_at: str


def _resp(row) -> ApiResponse[FeedbackResponse]:
    return ApiResponse[FeedbackResponse](data=FeedbackResponse(**repo.row_to_response_dict(row)))


@router.post("", status_code=201, response_model=ApiResponse[FeedbackResponse])
def create_feedback(payload: FeedbackCreate) -> ApiResponse[FeedbackResponse]:
    if run_repo.get_query_run(payload.query_run_id) is None:
        raise HTTPException(status_code=400, detail="query_run_id mevcut değil")
    row = repo.create_feedback(
        payload.query_run_id,
        payload.verdict.value,
        payload.category.value if payload.category is not None else None,
        payload.note,
        payload.corrected_sql,
    )
    return _resp(row)


@router.get("", response_model=ApiResponse[list[FeedbackResponse]])
def list_feedback(
    query_run_id: Optional[str] = Query(default=None),
    verdict: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ApiResponse[list[FeedbackResponse]]:
    rows = repo.list_feedback(limit=limit, offset=offset, query_run_id=query_run_id, verdict=verdict)
    data = [FeedbackResponse(**repo.row_to_response_dict(r)) for r in rows]
    meta = ResponseMeta(pagination=PageMeta(limit=limit, offset=offset, count=len(data)))
    return ApiResponse[list[FeedbackResponse]](data=data, meta=meta)


@router.get("/{feedback_id}", response_model=ApiResponse[FeedbackResponse])
def get_feedback(feedback_id: str) -> ApiResponse[FeedbackResponse]:
    row = repo.get_feedback(feedback_id)
    if row is None:
        raise HTTPException(status_code=404, detail="feedback bulunamadı")
    return _resp(row)


@router.delete("/{feedback_id}", response_model=ApiResponse[FeedbackResponse])
def delete_feedback(feedback_id: str) -> ApiResponse[FeedbackResponse]:
    row = repo.get_feedback(feedback_id)
    if row is None:
        raise HTTPException(status_code=404, detail="feedback bulunamadı")
    if not repo.delete_feedback(feedback_id):
        raise HTTPException(status_code=404, detail="feedback bulunamadı")
    return _resp(row)
