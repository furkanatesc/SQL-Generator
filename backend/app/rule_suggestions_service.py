"""Feedback -> kural onerisi adaptoru (Sprint 27.9).

KIRLI katman: feedback + jobs DB'ye dokunur. Saf birlestirme app.rule_suggestions
icindedir. Hesaplama YAN ETKISIZDIR: yazma yok, trace emit yok, LLM yok.
list_feedback (27.7) pencere-filtreli feedback'i ceker; her benzersiz job_id icin
get_job bir kez cagrilir (job cache). DB hatasi YUTULMAZ. Redaksiyon YOK
(corrected/result_sql ham SQL tasir; amac tam SQL'i onaya sunmak).
"""
from typing import Optional

from app.database import get_job, list_feedback
from app.rule_suggestions import SuggestionWindow, compute_rule_suggestions

SCAN_CAP = 10000


def build_rule_suggestions(*, created_after: Optional[str] = None,
                           created_before: Optional[str] = None,
                           scan_cap: int = SCAN_CAP) -> dict:
    rows = list(list_feedback(created_after=created_after,
                              created_before=created_before, limit=scan_cap + 1) or [])
    truncated = len(rows) > scan_cap
    rows = rows[:scan_cap]

    job_cache: dict = {}
    items = []
    for feedback in rows:
        job_id = feedback.get("job_id")
        if job_id not in job_cache:
            job_cache[job_id] = get_job(job_id) if job_id else None
        items.append((feedback, job_cache[job_id]))

    window = SuggestionWindow(
        created_after=created_after, created_before=created_before,
        feedback_count=len(items), eligible_count=0, suggestion_count=0,
        truncated=truncated, scan_cap=scan_cap)

    return compute_rule_suggestions(items, window).to_payload()
