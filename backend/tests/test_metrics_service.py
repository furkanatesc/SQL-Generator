import pytest

from app.metrics_service import compute_metrics_for_window, SCAN_CAP


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


def _rec(payload):
    class _R:
        pass
    r = _R()
    r.payload = payload
    return r


def _trace(terminal="completed", total_ms=10):
    return {"terminal_status": terminal, "total_duration_ms": total_ms,
            "spans": [{"stage": "intent", "status": "ok", "attributes": {}}]}


def test_window_meta_and_query_filters():
    store = _FakeStore(records=[_rec(_trace()), _rec(_trace("failed", 20))])
    out = compute_metrics_for_window(trace_store=store, created_after="2026-01-01",
                                     dialect="postgres")
    # out IS the metrics payload (version/window/outcome/...); router bunu {status,metrics}'e sarar
    assert out["version"] == "metrics_v1"
    assert out["window"]["trace_count"] == 2
    assert out["window"]["truncated"] is False
    assert out["window"]["created_after"] == "2026-01-01"
    assert out["window"]["dialect"] == "postgres"
    assert out["window"]["scan_cap"] == SCAN_CAP
    # end_to_end trace_type + limit=scan_cap+1 ile sorgulanmali
    assert store.last_query.trace_type == "end_to_end"
    assert store.last_query.limit == SCAN_CAP + 1
    assert out["outcome"]["total"] == 2


def test_truncation_flag_when_over_cap():
    recs = [_rec(_trace()) for _ in range(5)]
    out = compute_metrics_for_window(trace_store=_FakeStore(records=recs), scan_cap=3)
    assert out["window"]["truncated"] is True
    assert out["window"]["trace_count"] == 3          # cap uygulandi
    assert out["outcome"]["total"] == 3


def test_empty_window_is_ok():
    out = compute_metrics_for_window(trace_store=_FakeStore(records=[]))
    assert out["window"]["trace_count"] == 0
    assert out["outcome"]["total"] == 0
    assert out["outcome"]["success_rate"] is None


def test_store_error_propagates():
    with pytest.raises(RuntimeError):
        compute_metrics_for_window(trace_store=_FakeStore(raises=True))


def test_accepts_dict_shaped_records():
    store = _FakeStore(records=[{"payload": _trace()}])
    out = compute_metrics_for_window(trace_store=store)
    assert out["outcome"]["total"] == 1
