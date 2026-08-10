"""run_pipeline result-cache lookup/store (Sprint 28.9, Task 4)."""
import pytest
import app.sql_pipeline as sp
from app.sql_pipeline import SQLGenerationPipeline, ValidationOutcome


class _FakeSM:
    def __init__(self, sig):
        self._sig = sig

    def get_cached_schema_signature(self):
        return self._sig


def _valid_outcome(sql="SELECT 1"):
    return ValidationOutcome(sql=sql, valid=True, retry_disposition="ok",
                             validation_errors=[], error_message=None,
                             timings={"validation": 1, "security": 1}, pretty_printed=True)


def _pipeline(monkeypatch, *, sig="SIG", cache_config=None):
    p = SQLGenerationPipeline(schema_manager=_FakeSM(sig))
    # retrieval returns a fixed pruned schema (bypass real pruning)
    monkeypatch.setattr(p, "_stage_retrieval",
                        lambda **k: ({"tables": {"t": {}}}, "ctx", {"selector_version": "v"}, None, 3))
    monkeypatch.setattr(sp, "get_config",
                        lambda k: (cache_config if k == "sql_result_cache_enabled" else None))
    return p


def test_cache_hit_skips_writer_critic(monkeypatch):
    p = _pipeline(monkeypatch)
    monkeypatch.setattr(sp, "get_cached_sql", lambda key: "SELECT 1")
    monkeypatch.setattr(p, "validate_sql", lambda *a, **k: _valid_outcome("SELECT 1"))
    bumped = {"n": 0}
    monkeypatch.setattr(sp, "bump_hit", lambda key: bumped.__setitem__("n", bumped["n"] + 1))
    wc_called = {"n": 0}
    monkeypatch.setattr(p, "_stage_writer_critic",
                        lambda **k: (_ for _ in ()).throw(AssertionError("writer-critic must be skipped on hit")))
    res = p.run_pipeline(natural_query="list doctors", dialect="postgres")
    assert res["success"] is True
    assert res["generated_sql"] == "SELECT 1"
    assert res["cache_hit"] is True
    assert bumped["n"] == 1


def test_cache_miss_generates_and_stores(monkeypatch):
    p = _pipeline(monkeypatch)
    monkeypatch.setattr(sp, "get_cached_sql", lambda key: None)
    stored = {}
    monkeypatch.setattr(sp, "put_cached_sql",
                        lambda key, sql, dialect, sig: stored.update(key=key, sql=sql))

    def _fake_wc(**k):
        k["result"]["success"] = True
        k["result"]["generated_sql"] = "SELECT 42"
        return ({"last_generated_sql": "SELECT 42", "validation_errors": [],
                 "prompt_sha256": None, "prompt_char_count": None, "natural_query": "list doctors"},
                {"prompt": 1, "generation": 5, "validation": 1, "security": 1})
    monkeypatch.setattr(p, "_stage_writer_critic", _fake_wc)
    res = p.run_pipeline(natural_query="list doctors", dialect="postgres")
    assert res["success"] is True
    assert res["cache_hit"] is False
    assert stored["sql"] == "SELECT 42"


def test_hit_but_invalid_falls_through_to_generation(monkeypatch):
    p = _pipeline(monkeypatch)
    monkeypatch.setattr(sp, "get_cached_sql", lambda key: "SELECT stale")
    monkeypatch.setattr(p, "validate_sql", lambda *a, **k: ValidationOutcome(
        sql="SELECT stale", valid=False, retry_disposition="retry",
        validation_errors=[{"type": "x"}], error_message="bad", timings={"validation": 1, "security": 1}))
    wc_called = {"n": 0}

    def _fake_wc(**k):
        wc_called["n"] += 1
        k["result"]["success"] = True
        k["result"]["generated_sql"] = "SELECT fresh"
        return ({"last_generated_sql": "SELECT fresh", "validation_errors": [],
                 "prompt_sha256": None, "prompt_char_count": None, "natural_query": "q"},
                {"prompt": 1, "generation": 5, "validation": 1, "security": 1})
    monkeypatch.setattr(sp, "put_cached_sql", lambda *a, **k: None)
    monkeypatch.setattr(p, "_stage_writer_critic", _fake_wc)
    res = p.run_pipeline(natural_query="q", dialect="postgres")
    assert wc_called["n"] == 1
    assert res["cache_hit"] is False
    assert res["generated_sql"] == "SELECT fresh"


def test_no_signature_disables_cache(monkeypatch):
    p = _pipeline(monkeypatch, sig=None)   # get_cached_schema_signature -> None
    called = {"get": 0}
    monkeypatch.setattr(sp, "get_cached_sql", lambda key: called.__setitem__("get", called["get"] + 1) or "X")

    def _fake_wc(**k):
        k["result"]["success"] = True
        k["result"]["generated_sql"] = "SELECT 9"
        return ({"last_generated_sql": "SELECT 9", "validation_errors": [], "prompt_sha256": None,
                 "prompt_char_count": None, "natural_query": "q"},
                {"prompt": 1, "generation": 5, "validation": 1, "security": 1})
    monkeypatch.setattr(p, "_stage_writer_critic", _fake_wc)
    res = p.run_pipeline(natural_query="q", dialect="postgres")
    assert called["get"] == 0            # cache never consulted
    assert res["cache_hit"] is False


def test_disabled_config_always_generates(monkeypatch):
    p = _pipeline(monkeypatch, cache_config="off")
    called = {"get": 0}
    monkeypatch.setattr(sp, "get_cached_sql", lambda key: called.__setitem__("get", called["get"] + 1) or "X")

    def _fake_wc(**k):
        k["result"]["success"] = True
        k["result"]["generated_sql"] = "SELECT 9"
        return ({"last_generated_sql": "SELECT 9", "validation_errors": [], "prompt_sha256": None,
                 "prompt_char_count": None, "natural_query": "q"},
                {"prompt": 1, "generation": 5, "validation": 1, "security": 1})
    monkeypatch.setattr(p, "_stage_writer_critic", _fake_wc)
    res = p.run_pipeline(natural_query="q", dialect="postgres")
    assert called["get"] == 0
    assert res["cache_hit"] is False
