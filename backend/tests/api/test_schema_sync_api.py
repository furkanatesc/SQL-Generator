import json
import pytest
from fastapi.testclient import TestClient

import app.api.schema_sync_api as api
from app.main import app
from app.schema.schema_signature import compute_schema_signature

client = TestClient(app)
HEADERS = {"X-API-Key": "sqlgen_secret_dev_key"}
_SIG_EMPTY = compute_schema_signature({})

_NORM_A = {"t": {"columns": (("id", "INTEGER", True, False),), "foreign_keys": ()}}
_NORM_B = {"t": {"columns": (("id", "INTEGER", True, False),
                             ("email", "TEXT", False, True)), "foreign_keys": ()}}


class _FakeMgr:
    def __init__(self, current_norm, current_sig):
        self._n, self._s = current_norm, current_sig

    def _current_normalized_structure(self):
        return self._n

    def _current_schema_signature(self):
        return self._s


@pytest.fixture
def wire(monkeypatch, tmp_path):
    def _install(*, cache, current_norm, current_sig):
        cache_path = tmp_path / "schema_cache.json"
        if cache is not None:
            cache_path.write_text(json.dumps(cache), encoding="utf-8")
        monkeypatch.setattr(api, "CACHE_PATH", str(cache_path))
        monkeypatch.setattr(api, "SchemaManager",
                            lambda: _FakeMgr(current_norm, current_sig))
    return _install


def test_drift_false_when_signature_matches(wire):
    wire(cache={"schema_signature": _SIG_EMPTY, "schema": {"tables": {}, "graph": {}}},
         current_norm={}, current_sig=_SIG_EMPTY)
    r = client.get("/api/debug/schema/drift", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["drifted"] is False
    assert body["current_signature"] == _SIG_EMPTY


def test_drift_true_reports_added_column(wire):
    wire(cache={"schema_signature": "OLD",
                "schema": {"tables": {"t": {"columns": [
                    {"name": "id", "type": "INTEGER", "primary_key": True, "nullable": False}],
                    "foreign_keys": []}}, "graph": {}}},
         current_norm=_NORM_B, current_sig="NEW")
    r = client.get("/api/debug/schema/drift", headers=HEADERS)
    body = r.json()
    assert body["drifted"] is True
    assert {"table": "t", "column": "email"} in body["drift"]["added_columns"]


def test_drift_true_when_no_cache(wire):
    wire(cache=None, current_norm=_NORM_A, current_sig="NEW")
    r = client.get("/api/debug/schema/drift", headers=HEADERS)
    body = r.json()
    assert body["drifted"] is True
    assert body["cached_signature"] is None


def test_drift_requires_api_key(wire):
    wire(cache=None, current_norm=_NORM_A, current_sig="NEW")
    assert client.get("/api/debug/schema/drift").status_code == 403


def test_drift_404_when_debug_disabled(wire, monkeypatch):
    wire(cache=None, current_norm=_NORM_A, current_sig="NEW")

    class _Off:
        debug_endpoints_enabled = False
    monkeypatch.setattr(api, "get_settings", lambda: _Off())
    assert client.get("/api/debug/schema/drift", headers=HEADERS).status_code == 404


def test_sync_rebuilds_when_drifted(wire, monkeypatch):
    wire(cache={"schema_signature": "OLD", "schema": {"tables": {}, "graph": {}}},
         current_norm=_NORM_A, current_sig="NEW")
    called = {"n": 0}

    class _M2:
        def _current_normalized_structure(self): return _NORM_A
        def _current_schema_signature(self): return "NEW"
        def load_schema(self, force_refresh=False): called["n"] += 1; return {}
    monkeypatch.setattr(api, "SchemaManager", _M2)
    r = client.post("/api/debug/schema/sync", headers=HEADERS)
    assert r.status_code == 200
    assert r.json()["action"] == "rebuilt"
    assert called["n"] == 1


def test_sync_skips_rebuild_when_up_to_date(wire, monkeypatch):
    wire(cache={"schema_signature": _SIG_EMPTY, "schema": {"tables": {}, "graph": {}}},
         current_norm={}, current_sig=_SIG_EMPTY)
    called = {"n": 0}

    class _M2:
        def _current_normalized_structure(self): return {}
        def _current_schema_signature(self): return _SIG_EMPTY
        def load_schema(self, force_refresh=False): called["n"] += 1; return {}
    monkeypatch.setattr(api, "SchemaManager", _M2)
    r = client.post("/api/debug/schema/sync", headers=HEADERS)
    assert r.json()["action"] == "up_to_date"
    assert called["n"] == 0


def test_sync_force_rebuilds_when_up_to_date(wire, monkeypatch):
    wire(cache={"schema_signature": _SIG_EMPTY, "schema": {"tables": {}, "graph": {}}},
         current_norm={}, current_sig=_SIG_EMPTY)
    called = {"n": 0}

    class _M2:
        def _current_normalized_structure(self): return {}
        def _current_schema_signature(self): return _SIG_EMPTY
        def load_schema(self, force_refresh=False): called["n"] += 1; return {}
    monkeypatch.setattr(api, "SchemaManager", _M2)
    r = client.post("/api/debug/schema/sync?force=true", headers=HEADERS)
    assert r.json()["action"] == "rebuilt"
    assert called["n"] == 1


def test_sync_404_when_debug_disabled(wire, monkeypatch):
    wire(cache=None, current_norm=_NORM_A, current_sig="NEW")

    class _Off:
        debug_endpoints_enabled = False
    monkeypatch.setattr(api, "get_settings", lambda: _Off())
    assert client.post("/api/debug/schema/sync", headers=HEADERS).status_code == 404
