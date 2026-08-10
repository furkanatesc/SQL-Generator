"""get_cached_schema_signature reads schema_signature from cache file, no extract (28.9)."""
import json
import app.schema_manager as sm


def _mgr(monkeypatch, tmp_path):
    monkeypatch.setattr(sm, "get_db_connection_params",
                        lambda: {"type": "sqlite", "sqlite_path": ":memory:"})
    monkeypatch.setattr(sm, "CACHE_PATH", str(tmp_path / "schema_cache.json"))
    return sm.SchemaManager()


def test_returns_signature_from_cache(monkeypatch, tmp_path):
    m = _mgr(monkeypatch, tmp_path)
    with open(sm.CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump({"schema_signature": "SIG123", "schema": {"tables": {}}}, f)
    assert m.get_cached_schema_signature() == "SIG123"


def test_returns_none_when_no_file(monkeypatch, tmp_path):
    m = _mgr(monkeypatch, tmp_path)
    assert m.get_cached_schema_signature() is None


def test_returns_none_when_field_absent(monkeypatch, tmp_path):
    m = _mgr(monkeypatch, tmp_path)
    with open(sm.CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump({"schema": {"tables": {}}}, f)   # legacy cache, no signature
    assert m.get_cached_schema_signature() is None


def test_returns_none_on_malformed(monkeypatch, tmp_path):
    m = _mgr(monkeypatch, tmp_path)
    with open(sm.CACHE_PATH, "w", encoding="utf-8") as f:
        f.write("{not json")
    assert m.get_cached_schema_signature() is None
