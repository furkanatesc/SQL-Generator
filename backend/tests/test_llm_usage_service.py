from datetime import datetime, timezone
import pytest

from app.llm_usage_service import build_llm_usage, SCAN_CAP


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


def _payload(model="m1", pt=100, ct=20, tt=120):
    return {"spans": [{"stage": "generation", "status": "ok", "duration_ms": 500,
                       "detail": {"provider_id": "nvidia", "model_id": model,
                                  "finish_reason": "stop", "prompt_tokens": pt,
                                  "completion_tokens": ct, "total_tokens": tt}}]}


def _install_config(monkeypatch, value):
    monkeypatch.setattr("app.llm_usage_service.get_config", lambda key: value)


def test_single_fetch_and_pricing(monkeypatch):
    _install_config(monkeypatch, '{"currency":"USD","models":{"m1":{"input_per_1m":1000000,"output_per_1m":0}}}')
    recs = [_rec(_payload("m1", 2, 0, 2), datetime(2026, 8, 1, 10, tzinfo=timezone.utc))]
    store = _FakeStore(records=recs)
    out = build_llm_usage(trace_store=store, bucket="day")
    assert out["version"] == "llm_usage_v1"
    assert out["currency"] == "USD"
    assert out["window"]["trace_count"] == 1
    assert out["window"]["generation_count"] == 1
    assert out["totals"]["estimated_cost"] == 2.0   # 2 token * 1$/token
    # end_to_end + limit=cap+1 ile sorgulanmali
    assert store.last_query.trace_type == "end_to_end"
    assert store.last_query.limit == SCAN_CAP + 1


def test_truncation_flag(monkeypatch):
    _install_config(monkeypatch, None)
    recs = [_rec(_payload(), datetime(2026, 8, 1, tzinfo=timezone.utc)) for _ in range(5)]
    out = build_llm_usage(trace_store=_FakeStore(records=recs), scan_cap=3)
    assert out["window"]["truncated"] is True
    assert out["window"]["trace_count"] == 3


def test_empty_window_ok(monkeypatch):
    _install_config(monkeypatch, None)
    out = build_llm_usage(trace_store=_FakeStore(records=[]))
    assert out["window"]["trace_count"] == 0
    assert out["totals"]["total_tokens"] == 0
    assert out["by_model"] == [] and out["timeseries"] == []
    assert out["currency"] == "USD"   # config yok -> default


def test_invalid_pricing_json_falls_back(monkeypatch):
    _install_config(monkeypatch, "{not json")
    recs = [_rec(_payload("m1", 100, 0, 100), datetime(2026, 8, 1, tzinfo=timezone.utc))]
    out = build_llm_usage(trace_store=_FakeStore(records=recs))
    assert out["totals"]["estimated_cost"] == 0.0        # fiyat yok
    assert out["pricing"]["models_missing_price"] == ["m1"]


def test_store_error_propagates(monkeypatch):
    _install_config(monkeypatch, None)
    with pytest.raises(RuntimeError):
        build_llm_usage(trace_store=_FakeStore(raises=True))


def test_accepts_dict_shaped_records(monkeypatch):
    _install_config(monkeypatch, None)
    rec = {"payload": _payload(), "created_at": datetime(2026, 8, 1, tzinfo=timezone.utc)}
    out = build_llm_usage(trace_store=_FakeStore(records=[rec]))
    assert out["window"]["trace_count"] == 1
    assert out["window"]["generation_count"] == 1
