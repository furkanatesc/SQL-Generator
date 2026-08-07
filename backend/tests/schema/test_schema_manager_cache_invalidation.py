"""Integration tests for fingerprint-based schema cache invalidation (Sprint 28.6, Task 2).

Verifies SchemaManager.load_schema re-extracts the schema when the cache
fingerprint (db_type + hidden_tables/columns config + embedding model +
SCHEMA_CACHE_VERSION) no longer matches the current environment, and reuses
the cache when it does. Isolates load_schema from the real DB, embeddings,
and Qdrant via monkeypatch.
"""
import json

import app.schema_manager as sm


class _FakeEmbedder:
    class _Client:
        model = "fake_model_v1"

    def __init__(self, *a, **k):
        self.embedding_client = self._Client()

    def build_index(self, schema, api_key=None):
        return {}


class _FakeRAG:
    def index_schema_batch(self, schema):
        pass


def _mgr(monkeypatch, tmp_path, hidden_tables="[]"):
    monkeypatch.setattr(sm, "get_db_connection_params",
                         lambda: {"type": "sqlite", "sqlite_path": ":memory:"})
    monkeypatch.setattr(sm, "CACHE_PATH", str(tmp_path / "schema_cache.json"))
    monkeypatch.setattr(sm, "SchemaEmbeddingIndex", _FakeEmbedder)
    # get_config is imported locally inside load_schema via
    # `from app.database import get_config` -> patch it at the definition site.
    cfg = {"hidden_tables_sqlite": hidden_tables, "hidden_columns_sqlite": "{}"}
    monkeypatch.setattr("app.database.get_config", lambda k: cfg.get(k))
    # RAGManager is imported inside load_schema via `from app.rag_manager import RAGManager`.
    monkeypatch.setattr("app.rag_manager.RAGManager", lambda *a, **k: _FakeRAG())
    m = sm.SchemaManager()
    calls = {"extract": 0}

    def fake_extract():
        calls["extract"] += 1
        return {"tables": {"t": {"columns": [{"name": "id"}], "foreign_keys": []}},
                 "graph": {"nodes": ["t"], "edges": []}}

    monkeypatch.setattr(m, "extract_schema_metadata", fake_extract)
    return m, calls


def test_matching_fingerprint_uses_cache_no_extract(monkeypatch, tmp_path):
    m, calls = _mgr(monkeypatch, tmp_path)
    m.load_schema()                       # first load: extract + write cache
    assert calls["extract"] == 1
    m.load_schema()                       # second load: fingerprint matches -> cache used
    assert calls["extract"] == 1          # NOT re-extracted


def test_hidden_tables_config_change_reextracts(monkeypatch, tmp_path):
    m, calls = _mgr(monkeypatch, tmp_path)
    m.load_schema()
    assert calls["extract"] == 1
    # change the hidden_tables config -> fingerprint changes -> re-extract
    monkeypatch.setattr("app.database.get_config",
                         lambda k: {"hidden_tables_sqlite": '["t"]',
                                    "hidden_columns_sqlite": "{}"}.get(k))
    m.load_schema()
    assert calls["extract"] == 2


def test_legacy_cache_without_fingerprint_reextracts(monkeypatch, tmp_path):
    m, calls = _mgr(monkeypatch, tmp_path)
    # seed a legacy cache file with NO cache_fingerprint
    with open(sm.CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump({"db_type": "sqlite", "schema": {"tables": {}}, "embeddings": {"model": "x", "tables": {}}}, f)
    m.load_schema()
    assert calls["extract"] == 1          # legacy cache invalidated once


def test_force_refresh_always_reextracts(monkeypatch, tmp_path):
    m, calls = _mgr(monkeypatch, tmp_path)
    m.load_schema()
    m.load_schema(force_refresh=True)
    assert calls["extract"] == 2
