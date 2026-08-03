"""Feedback -> kural onerisi hesaplama — SAF (Sprint 27.9).

I/O yok. datetime.now() ASLA. category/verdict sinirdan plain string gelir
(app.feedback import edilmez). Yalniz stdlib + app.rule_suggestions.contract.
"""
from typing import Optional

CORRECTION = "correction"
CONFIRMATION = "confirmation"


def _clean(s) -> str:
    return s.strip() if isinstance(s, str) else ""


def classify_item(feedback: dict, job: Optional[dict]) -> dict:
    """Bir (feedback, job) ciftini eligible bir oneriye ya da ineligible-sebebe ayirir.

    Ineligible sebep onceligi: missing_job > missing_natural_query > missing_sql.
    - incorrect + bos-olmayan corrected_sql -> correction (category = feedback.category)
    - correct   + bos-olmayan job.result_sql -> confirmation (category = None)
    - bilinmeyen verdict / SQL hedefi yok -> ineligible: missing_sql
    """
    if job is None:
        return {"status": "ineligible", "reason": "missing_job"}
    natural_query = _clean(job.get("natural_query"))
    if not natural_query:
        return {"status": "ineligible", "reason": "missing_natural_query"}

    verdict = feedback.get("verdict")
    if verdict == "incorrect":
        sql = _clean(feedback.get("corrected_sql"))
        if not sql:
            return {"status": "ineligible", "reason": "missing_sql"}
        return {"status": "eligible", "kind": CORRECTION, "natural_query": natural_query,
                "suggested_sql": sql, "category": feedback.get("category"),
                "feedback_id": feedback.get("id"), "job_id": feedback.get("job_id")}
    if verdict == "correct":
        sql = _clean(job.get("result_sql"))
        if not sql:
            return {"status": "ineligible", "reason": "missing_sql"}
        return {"status": "eligible", "kind": CONFIRMATION, "natural_query": natural_query,
                "suggested_sql": sql, "category": None,
                "feedback_id": feedback.get("id"), "job_id": feedback.get("job_id")}
    # bilinmeyen verdict: turetilebilir bir SQL hedefi yok
    return {"status": "ineligible", "reason": "missing_sql"}
