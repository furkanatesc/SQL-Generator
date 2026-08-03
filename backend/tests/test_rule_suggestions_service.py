import pytest

from app.rule_suggestions_service import build_rule_suggestions, SCAN_CAP


def _install(monkeypatch, feedback_rows, jobs, feedback_raises=False):
    def _lf(created_after=None, created_before=None, limit=10000):
        if feedback_raises:
            raise RuntimeError("db patladi")
        return list(feedback_rows)
    monkeypatch.setattr("app.rule_suggestions_service.list_feedback", _lf)
    monkeypatch.setattr("app.rule_suggestions_service.get_job", lambda job_id: jobs.get(job_id))


def _fb(verdict, fid, job_id, corrected_sql=None, category=None):
    return {"id": fid, "job_id": job_id, "verdict": verdict,
            "category": category, "corrected_sql": corrected_sql}


def test_correlates_feedback_with_jobs(monkeypatch):
    feedback = [
        _fb("incorrect", "f1", "j1", corrected_sql="SELECT 1", category="wrong_filter"),
        _fb("correct", "f2", "j2"),
    ]
    jobs = {"j1": {"natural_query": "q1", "result_sql": None},
            "j2": {"natural_query": "q2", "result_sql": "SELECT 2"}}
    _install(monkeypatch, feedback, jobs)
    out = build_rule_suggestions()
    assert out["version"] == "rule_suggestions_v1"
    assert out["window"]["feedback_count"] == 2
    assert out["window"]["suggestion_count"] == 2
    kinds = {s["kind"] for s in out["suggestions"]}
    assert kinds == {"correction", "confirmation"}


def test_unique_job_fetch(monkeypatch):
    # ayni job_id iki feedback -> get_job bir kez cagrilmali
    calls = {"n": 0}
    feedback = [_fb("incorrect", "f1", "j1", corrected_sql="SELECT 1"),
                _fb("incorrect", "f2", "j1", corrected_sql="SELECT 1")]
    monkeypatch.setattr("app.rule_suggestions_service.list_feedback",
                        lambda created_after=None, created_before=None, limit=10000: list(feedback))

    def _get_job(job_id):
        calls["n"] += 1
        return {"natural_query": "q", "result_sql": None}
    monkeypatch.setattr("app.rule_suggestions_service.get_job", _get_job)
    out = build_rule_suggestions()
    assert calls["n"] == 1                      # tek benzersiz job
    assert out["suggestions"][0]["support_count"] == 2


def test_missing_job_ineligible(monkeypatch):
    _install(monkeypatch, [_fb("incorrect", "f1", "jX", corrected_sql="SELECT 1")], {})  # job yok
    out = build_rule_suggestions()
    assert out["suggestions"] == []
    assert out["ineligible"]["reasons"] == {"missing_job": 1}


def test_truncation_flag(monkeypatch):
    feedback = [_fb("correct", f"f{i}", f"j{i}") for i in range(5)]
    jobs = {f"j{i}": {"natural_query": f"q{i}", "result_sql": "SELECT 1"} for i in range(5)}
    _install(monkeypatch, feedback, jobs)
    out = build_rule_suggestions(scan_cap=3)
    assert out["window"]["truncated"] is True
    assert out["window"]["feedback_count"] == 3


def test_empty_and_error(monkeypatch):
    _install(monkeypatch, [], {})
    out = build_rule_suggestions()
    assert out["window"]["feedback_count"] == 0 and out["suggestions"] == []

    _install(monkeypatch, [], {}, feedback_raises=True)
    with pytest.raises(RuntimeError):
        build_rule_suggestions()
