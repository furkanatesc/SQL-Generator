import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
HEADERS = {"X-API-Key": "sqlgen_secret_dev_key"}

_SAMPLE = {
    "version": "rule_suggestions_v1",
    "window": {"created_after": None, "created_before": None, "feedback_count": 0,
               "eligible_count": 0, "suggestion_count": 0, "truncated": False,
               "scan_cap": 10000},
    "suggestions": [], "by_kind": {}, "by_category": {},
    "ineligible": {"total": 0, "reasons": {}},
}


@pytest.fixture
def fake_suggestions(monkeypatch):
    def _install(payload=None):
        def _bs(*, created_after=None, created_before=None, scan_cap=10000):
            return payload or _SAMPLE
        monkeypatch.setattr("app.api.rule_suggestions_api.build_rule_suggestions", _bs)
    return _install


def test_200_success_envelope(fake_suggestions):
    fake_suggestions()
    r = client.get("/api/debug/rule-suggestions", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "success"
    assert body["suggestions"]["version"] == "rule_suggestions_v1"


def test_passes_query_params(monkeypatch):
    seen = {}

    def _bs(*, created_after=None, created_before=None, scan_cap=10000):
        seen.update(created_after=created_after, created_before=created_before)
        return _SAMPLE
    monkeypatch.setattr("app.api.rule_suggestions_api.build_rule_suggestions", _bs)
    r = client.get("/api/debug/rule-suggestions?created_after=2026-08-01T00:00:00",
                   headers=HEADERS)
    assert r.status_code == 200
    assert seen == {"created_after": "2026-08-01T00:00:00", "created_before": None}


def test_requires_api_key(fake_suggestions):
    fake_suggestions()
    assert client.get("/api/debug/rule-suggestions").status_code == 403


def test_404_when_debug_disabled(fake_suggestions, monkeypatch):
    fake_suggestions()

    class _Off:
        debug_endpoints_enabled = False
    monkeypatch.setattr("app.api.rule_suggestions_api.get_settings", lambda: _Off())
    assert client.get("/api/debug/rule-suggestions", headers=HEADERS).status_code == 404
