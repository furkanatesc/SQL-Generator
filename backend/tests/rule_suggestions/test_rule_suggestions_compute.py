from app.rule_suggestions import (
    compute_rule_suggestions, SuggestionWindow, RULE_SUGGESTIONS_CONTRACT_VERSION,
)


def _win():
    return SuggestionWindow(created_after=None, created_before=None, feedback_count=0,
                            eligible_count=0, suggestion_count=0, truncated=False, scan_cap=10000)


def _fb(verdict, fid, job_id, corrected_sql=None, category=None):
    return {"id": fid, "job_id": job_id, "verdict": verdict,
            "category": category, "corrected_sql": corrected_sql}


def _job(nl, result_sql=None):
    return {"natural_query": nl, "result_sql": result_sql}


def test_dedup_support_and_ranking():
    items = [
        # ayni (nl, sql, correction) iki feedback -> support 2
        (_fb("incorrect", "f1", "j1", corrected_sql="SELECT 1", category="wrong_filter"), _job("q1")),
        (_fb("incorrect", "f2", "j2", corrected_sql="SELECT 1", category="wrong_join"), _job("q1")),
        # tekil confirmation
        (_fb("correct", "f3", "j3"), _job("q2", result_sql="SELECT 2")),
    ]
    p = compute_rule_suggestions(items, _win()).to_payload()
    assert p["version"] == RULE_SUGGESTIONS_CONTRACT_VERSION
    assert p["window"]["feedback_count"] == 3
    assert p["window"]["eligible_count"] == 3
    assert p["window"]["suggestion_count"] == 2
    # support DESC -> deduped correction (support 2) once
    s0 = p["suggestions"][0]
    assert s0["support_count"] == 2 and s0["kind"] == "correction"
    assert s0["feedback_ids"] == ["f1", "f2"] and s0["job_ids"] == ["j1", "j2"]
    assert s0["categories"] == ["wrong_filter", "wrong_join"]   # distinct sirali
    assert p["by_kind"] == {"confirmation": 1, "correction": 1}
    # by_category: correction feedback bazinda (dedup-oncesi)
    assert p["by_category"] == {"wrong_filter": 1, "wrong_join": 1}


def test_ineligible_tally():
    items = [
        (_fb("incorrect", "f1", "j1", corrected_sql=None), _job("q")),   # missing_sql
        (_fb("correct", "f2", "j2"), None),                              # missing_job
        (_fb("correct", "f3", "j3"), _job("  ")),                        # missing_natural_query
    ]
    p = compute_rule_suggestions(items, _win()).to_payload()
    assert p["suggestions"] == []
    assert p["window"]["eligible_count"] == 0
    assert p["ineligible"]["total"] == 3
    assert p["ineligible"]["reasons"] == {"missing_job": 1, "missing_natural_query": 1, "missing_sql": 1}


def test_deterministic_and_empty():
    assert compute_rule_suggestions([], _win()).to_payload() == compute_rule_suggestions([], _win()).to_payload()
    p = compute_rule_suggestions([], _win()).to_payload()
    assert p["suggestions"] == [] and p["by_kind"] == {} and p["by_category"] == {}
    assert p["ineligible"] == {"total": 0, "reasons": {}}
