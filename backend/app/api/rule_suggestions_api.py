"""Feedback -> kural onerisi router (Sprint 27.9).

metrics_api/dashboard_api/llm_usage_api deseni: kendi APIRouter'i, main.py'de mount
edilir, debug_endpoints_enabled kapaliyken 404 doner. Hesaplama YAN ETKISIZDIR.
Bu endpoint trace store'a DOKUNMAZ (feedback+jobs DB okur) -> get_trace_store almaz.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.schemas import RuleSuggestionsEnvelopeResponse
from app.auth import verify_api_key
from app.rule_suggestions_service import build_rule_suggestions
from app.settings import get_settings

router = APIRouter(
    prefix="/api/debug/rule-suggestions",
    tags=["debug-rule-suggestions"],
    dependencies=[Depends(verify_api_key)],
)


def ensure_debug_enabled():
    if not get_settings().debug_endpoints_enabled:
        raise HTTPException(status_code=404, detail="Not found")


@router.get("", response_model=RuleSuggestionsEnvelopeResponse)
def rule_suggestions(
    created_after: Optional[str] = Query(default=None),
    created_before: Optional[str] = Query(default=None),
):
    ensure_debug_enabled()
    payload = build_rule_suggestions(
        created_after=created_after, created_before=created_before)
    return {"status": "success", "suggestions": payload}
