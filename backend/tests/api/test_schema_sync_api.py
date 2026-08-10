import json
import pytest
from fastapi.testclient import TestClient

import app.api.schema_sync_api as api
from app.main import app

client = TestClient(app)
HEADERS = {"X-API-Key": "sqlgen_secret_dev_key"}

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
    wire(cache={"schema_signature": "SIG", "schema": {"tables": {}, "graph": {}}},
         current_norm={}, current_sig="SIG")
    r = client.get("/api/debug/schema/drift", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["drifted"] is False
    assert body["current_signature"] == "SIG"


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
