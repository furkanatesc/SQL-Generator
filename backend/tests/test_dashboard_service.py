from datetime import datetime, timezone
import pytest

from app.dashboard_service import build_dashboard, SCAN_CAP


class _FakeStore:
    def __init__(self, records=None, raises=False):
        self._records = records or []
        self._raises = raises
        self.last_query = None

    def list_traces(self, query):
        self.last_query = query
        if self._raises:
            raise RuntimeError("store patladi")
        return list(self._records)


def _rec(payload, created_at):
    class _R:
        pass
    r = _R()
    r.payload = payload
    r.created_at = created_at
    return r


def _payload(terminal="completed", ms=10, h=10):
    return {"terminal_status": terminal, "total_duration_ms": ms, "job_id": f"j{h}",
            "trace_id": f"t{h}", "dialect": "postgres",
            "spans": [{"stage": "intent", "status": "ok", "attributes": {}}]}


def _install_feedback(monkeypatch, rows, raises=False):
    def _lf(created_after=None, created_before=None, limit=10000):
        if raises:
            raise RuntimeError("db patladi")
        return rows
    monkeypatch.setattr("app.dashboard_service.list_feedback", _lf)


def test_single_fetch_feeds_sections(monkeypatch):
    _install_feedback(monkeypatch, [{"verdict": "correct", "category": None}])
    recs = [_rec(_payload("completed", 10, 10), datetime(2026, 7, 31, 10, tzinfo=timezone.utc)),
            _rec(_payload("failed", 30, 11), datetime(2026, 7, 31, 11, tzinfo=timezone.utc))]
    out = build_dashboard(trace_store=_FakeStore(records=recs), bucket="day")
    assert out["version"] == "dashboard_v1"
    assert out["window"]["trace_count"] == 2
    assert out["window"]["bucket"] == "day"
    assert out["metrics"]["outcome"]["total"] == 2
    assert out["timeseries"][0]["total"] == 2
    assert out["feedback"]["total"] == 1
    assert len(out["recent_activity"]) == 2
    # end_to_end + limit=cap+1 ile sorgulanmali
    assert _FakeStore().list_traces.__name__  # sanity
    store = _FakeStore(records=recs)
    build_dashboard(trace_store=store, bucket="day")
    assert store.last_query.trace_type == "end_to_end"
    assert store.last_query.limit == SCAN_CAP + 1


def test_truncation_flag(monkeypatch):
    _install_feedback(monkeypatch, [])
    recs = [_rec(_payload(h=i), datetime(2026, 7, 31, tzinfo=timezone.utc)) for i in range(5)]
    out = build_dashboard(trace_store=_FakeStore(records=recs), scan_cap=3)
    assert out["window"]["truncated"] is True
    assert out["window"]["trace_count"] == 3


def test_empty_window_ok(monkeypatch):
    _install_feedback(monkeypatch, [])
    out = build_dashboard(trace_store=_FakeStore(records=[]))
    assert out["window"]["trace_count"] == 0
    assert out["metrics"]["outcome"]["total"] == 0
    assert out["timeseries"] == [] and out["recent_activity"] == []
    assert out["feedback"]["total"] == 0


def test_store_error_propagates(monkeypatch):
    _install_feedback(monkeypatch, [])
    with pytest.raises(RuntimeError):
        build_dashboard(trace_store=_FakeStore(raises=True))


def test_feedback_db_error_propagates(monkeypatch):
    _install_feedback(monkeypatch, [], raises=True)
    with pytest.raises(RuntimeError):
        build_dashboard(trace_store=_FakeStore(records=[]))


def test_accepts_dict_shaped_records(monkeypatch):
    _install_feedback(monkeypatch, [])
    rec = {"payload": _payload(), "created_at": datetime(2026, 7, 31, tzinfo=timezone.utc)}
    out = build_dashboard(trace_store=_FakeStore(records=[rec]))
    assert out["window"]["trace_count"] == 1


def test_feedback_truncated_flag(monkeypatch):
    # scan_cap'i asan feedback -> feedback_truncated True, feedback.total == scan_cap (§8.2)
    big = [{"id": f"f{i}", "job_id": f"j{i}", "verdict": "correct",
            "category": None, "created_at": "2026-08-01T00:00:00"} for i in range(5)]

    def _lf(created_after=None, created_before=None, limit=10000):
        return list(big)[:limit]
    monkeypatch.setattr("app.dashboard_service.list_feedback", _lf)

    out = build_dashboard(trace_store=_FakeStore(records=[]), scan_cap=3)
    assert out["window"]["feedback_truncated"] is True
    assert out["feedback"]["total"] == 3


def test_feedback_not_truncated_flag(monkeypatch):
    # scan_cap'i asmayan feedback -> feedback_truncated False (§8.2)
    small = [{"id": "f1", "job_id": "j1", "verdict": "correct",
              "category": None, "created_at": "2026-08-01T00:00:00"}]

    def _lf(created_after=None, created_before=None, limit=10000):
        return list(small)[:limit]
    monkeypatch.setattr("app.dashboard_service.list_feedback", _lf)

    out = build_dashboard(trace_store=_FakeStore(records=[]), scan_cap=3)
    assert out["window"]["feedback_truncated"] is False
    assert out["feedback"]["total"] == 1
