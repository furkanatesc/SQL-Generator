import json
from app.dashboard import (
    DASHBOARD_CONTRACT_VERSION, DashboardReport, DashboardWindow,
    TimeseriesBucket, TopError, FeedbackSummary, RecentTrace,
)


def _sample() -> DashboardReport:
    return DashboardReport(
        version=DASHBOARD_CONTRACT_VERSION,
        window=DashboardWindow(created_after=None, created_before=None, dialect="postgres",
                               trace_count=2, truncated=False, scan_cap=10000,
                               bucket="day", timeseries_truncated=False),
        metrics={"version": "metrics_v1"},
        timeseries=(TimeseriesBucket(bucket_start="2026-07-31T00:00:00+00:00", total=2,
                                     success_rate=0.5, error_count=1, p95_ms=40),),
        top_errors=(TopError(code="missing_column", category="validation", count=3),),
        feedback=FeedbackSummary(total=2, by_verdict={"incorrect": 1, "correct": 1},
                                 by_category={"wrong_columns": 1}),
        recent_activity=(RecentTrace(job_id="j1", trace_id="t1", terminal_status="failed",
                                     dialect="postgres", total_duration_ms=40,
                                     created_at="2026-07-31T10:00:00+00:00"),),
    )


def test_to_payload_json_safe_and_shaped():
    p = _sample().to_payload()
    json.dumps(p)
    assert p["version"] == "dashboard_v1"
    assert set(p.keys()) == {"version", "window", "metrics", "timeseries",
                             "top_errors", "feedback", "recent_activity"}
    assert p["timeseries"][0]["p95_ms"] == 40
    assert p["top_errors"][0]["category"] == "validation"
    assert p["window"]["bucket"] == "day"


def test_feedback_dicts_sorted_deterministic():
    fs = FeedbackSummary(total=3, by_verdict={"incorrect": 1, "correct": 2},
                         by_category={"wrong_table": 1, "missing_filter": 1})
    p = fs.to_payload()
    assert list(p["by_verdict"].keys()) == ["correct", "incorrect"]
    assert list(p["by_category"].keys()) == ["missing_filter", "wrong_table"]


def test_empty_sections_serialize():
    r = DashboardReport(
        version=DASHBOARD_CONTRACT_VERSION,
        window=DashboardWindow(None, None, None, 0, False, 10000, "day", False),
        metrics={}, timeseries=(), top_errors=(),
        feedback=FeedbackSummary(total=0, by_verdict={}, by_category={}),
        recent_activity=())
    p = r.to_payload()
    assert p["timeseries"] == [] and p["top_errors"] == [] and p["recent_activity"] == []
    assert p["feedback"] == {"total": 0, "by_verdict": {}, "by_category": {}}
