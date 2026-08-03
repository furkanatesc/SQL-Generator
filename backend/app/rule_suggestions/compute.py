"""Feedback -> kural onerisi hesaplama — SAF (Sprint 27.9).

I/O yok. datetime.now() ASLA. category/verdict sinirdan plain string gelir
(app.feedback import edilmez). Yalniz stdlib + app.rule_suggestions.contract.
"""
import dataclasses
from typing import Optional

from app.rule_suggestions.contract import (
    RULE_SUGGESTIONS_CONTRACT_VERSION,
    IneligibleSummary,
    RuleSuggestion,
    RuleSuggestionsReport,
)

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


def compute_rule_suggestions(items, window) -> RuleSuggestionsReport:
    eligibles = []
    reasons: dict = {}
    for feedback, job in items:
        r = classify_item(feedback, job)
        if r["status"] == "ineligible":
            reasons[r["reason"]] = reasons.get(r["reason"], 0) + 1
        else:
            eligibles.append(r)

    # by_category: correction feedback bazinda (dedup-oncesi, category dolu olanlar)
    by_category: dict = {}
    for e in eligibles:
        cat = e.get("category")
        if cat:
            by_category[cat] = by_category.get(cat, 0) + 1

    # dedup: (natural_query, suggested_sql, kind)
    groups: dict = {}
    for e in eligibles:
        key = (e["natural_query"], e["suggested_sql"], e["kind"])
        groups.setdefault(key, []).append(e)

    suggestions = []
    for key in groups:
        evs = groups[key]
        natural_query, suggested_sql, kind = key
        feedback_ids = tuple(sorted({e["feedback_id"] for e in evs if e["feedback_id"]}))
        job_ids = tuple(sorted({e["job_id"] for e in evs if e["job_id"]}))
        categories = tuple(sorted({e["category"] for e in evs if e["category"]}))
        suggestions.append(RuleSuggestion(
            natural_query=natural_query, suggested_sql=suggested_sql, kind=kind,
            categories=categories, support_count=len(evs),
            feedback_ids=feedback_ids, job_ids=job_ids))

    # siralama: support DESC, natural_query ASC, suggested_sql ASC
    suggestions.sort(key=lambda s: (-s.support_count, s.natural_query, s.suggested_sql))

    by_kind: dict = {}
    for s in suggestions:
        by_kind[s.kind] = by_kind.get(s.kind, 0) + 1

    window = dataclasses.replace(window, feedback_count=len(items),
                                 eligible_count=len(eligibles),
                                 suggestion_count=len(suggestions))
    ineligible = IneligibleSummary(total=sum(reasons.values()), reasons=reasons)

    return RuleSuggestionsReport(
        version=RULE_SUGGESTIONS_CONTRACT_VERSION, window=window,
        suggestions=tuple(suggestions), by_kind=by_kind, by_category=by_category,
        ineligible=ineligible)
