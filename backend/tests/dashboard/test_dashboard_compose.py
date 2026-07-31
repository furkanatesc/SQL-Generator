from datetime import datetime, timezone
from app.dashboard import compose_dashboard, DashboardWindow, DASHBOARD_CONTRACT_VERSION


def _win(n, truncated=False):
    return DashboardWindow(created_after=None, created_before=None, dialect="postgres",
                           trace_count=n, truncated=truncated, scan_cap=10000,
                           bucket="day", timeseries_truncated=False)


def _item(h, terminal, ms, code=None):
    spans = [{"stage": "retrieval", "status": "error",
              "attributes": {"reason_code": code}}] if code else \
            [{"stage": "intent", "status": "ok", "attributes": {}}]
    return (datetime(2026, 7, 31, h, tzinfo=timezone.utc),
            {"terminal_status": terminal, "total_duration_ms": ms,
             "job_id": f"j{h}", "trace_id": f"t{h}", "dialect": "postgres", "spans": spans})


def _args():
    items = [_item(10, "completed", 10),
             _item(11, "failed", 30, code="schema_pruning_failed")]
    return dict(
        trace_items=items,
        feedback_rows=[{"verdict": "incorrect", "category": "wrong_columns"}],
        window_base=_win(2),
        bucket="day", top_n=5, recent_limit=10)


def test_compose_builds_all_sections():
    p = compose_dashboard(**_args()).to_payload()
    assert p["version"] == DASHBOARD_CONTRACT_VERSION
    assert p["metrics"]["outcome"]["total"] == 2                # compute_metrics reuse
    assert p["metrics"]["outcome"]["terminal_status"] == {"completed": 1, "failed": 1}
    assert p["timeseries"][0]["bucket_start"] == "2026-07-31T00:00:00+00:00"
    assert p["timeseries"][0]["total"] == 2
    assert p["top_errors"][0]["code"] == "schema_pruning_failed"
    assert p["feedback"]["total"] == 1
    assert len(p["recent_activity"]) == 2
    assert p["window"]["timeseries_truncated"] is False


def test_compose_is_deterministic():
    assert compose_dashboard(**_args()).to_payload() == compose_dashboard(**_args()).to_payload()


def test_compose_empty_inputs():
    p = compose_dashboard(trace_items=[], feedback_rows=[], window_base=_win(0),
                          bucket="day", top_n=5, recent_limit=10).to_payload()
    assert p["metrics"]["outcome"]["total"] == 0
    assert p["timeseries"] == [] and p["top_errors"] == [] and p["recent_activity"] == []
    assert p["feedback"]["total"] == 0
