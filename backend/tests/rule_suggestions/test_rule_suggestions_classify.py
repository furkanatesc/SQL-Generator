from app.rule_suggestions import classify_item, CORRECTION, CONFIRMATION


def _fb(verdict, corrected_sql=None, category=None, fid="f1", job_id="j1"):
    return {"id": fid, "job_id": job_id, "verdict": verdict,
            "category": category, "corrected_sql": corrected_sql}


def _job(natural_query="q", result_sql=None):
    return {"natural_query": natural_query, "result_sql": result_sql}


def test_correction_eligible():
    r = classify_item(_fb("incorrect", corrected_sql="SELECT 1", category="wrong_filter"),
                      _job("aktif doktorlar"))
    assert r == {"status": "eligible", "kind": CORRECTION,
                 "natural_query": "aktif doktorlar", "suggested_sql": "SELECT 1",
                 "category": "wrong_filter", "feedback_id": "f1", "job_id": "j1"}


def test_confirmation_eligible():
    r = classify_item(_fb("correct"), _job("hasta sayisi", result_sql="SELECT COUNT(*)"))
    assert r["status"] == "eligible" and r["kind"] == CONFIRMATION
    assert r["suggested_sql"] == "SELECT COUNT(*)" and r["category"] is None


def test_strips_whitespace():
    r = classify_item(_fb("incorrect", corrected_sql="  SELECT 1  "), _job("  q  "))
    assert r["natural_query"] == "q" and r["suggested_sql"] == "SELECT 1"


def test_ineligible_missing_job_wins():
    r = classify_item(_fb("incorrect", corrected_sql="SELECT 1"), None)
    assert r == {"status": "ineligible", "reason": "missing_job"}


def test_ineligible_missing_natural_query_over_sql():
    # job var ama nl bos -> missing_natural_query (missing_sql'den once)
    r = classify_item(_fb("incorrect", corrected_sql=None), _job(natural_query="  "))
    assert r == {"status": "ineligible", "reason": "missing_natural_query"}


def test_ineligible_missing_sql_correction():
    r = classify_item(_fb("incorrect", corrected_sql="   "), _job("q"))
    assert r == {"status": "ineligible", "reason": "missing_sql"}


def test_ineligible_missing_sql_confirmation():
    r = classify_item(_fb("correct"), _job("q", result_sql=None))
    assert r == {"status": "ineligible", "reason": "missing_sql"}


def test_unknown_verdict_ineligible():
    r = classify_item(_fb("weird_verdict", corrected_sql="SELECT 1"), _job("q"))
    assert r["status"] == "ineligible" and r["reason"] == "missing_sql"
