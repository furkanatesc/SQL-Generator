"""schema_signature is persisted in the cache payload (Sprint 28.7, Task 3)."""
import json
import app.schema_manager as sm
from app.schema.schema_signature import compute_schema_signature, normalize_structure


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


_SCHEMA = {"tables": {"t": {"columns": [{"name": "id", "type": "INTEGER",
                                         "primary_key": True, "nullable": False}],
                            "foreign_keys": []}},
           "graph": {"nodes": ["t"], "edges": []}}


def _mgr(monkeypatch, tmp_path, cfg=None):
    monkeypatch.setattr(sm, "get_db_connection_params",
                        lambda: {"type": "sqlite", "sqlite_path": ":memory:"})
    monkeypatch.setattr(sm, "CACHE_PATH", str(tmp_path / "schema_cache.json"))
    monkeypatch.setattr(sm, "SchemaEmbeddingIndex", _FakeEmbedder)
    base_cfg = {"hidden_tables_sqlite": "[]", "hidden_columns_sqlite": "{}"}
    base_cfg.update(cfg or {})
    monkeypatch.setattr("app.database.get_config", lambda k: base_cfg.get(k))
    monkeypatch.setattr("app.rag_manager.RAGManager", lambda *a, **k: _FakeRAG())
    m = sm.SchemaManager()
    monkeypatch.setattr(m, "extract_schema_metadata", lambda: dict(_SCHEMA))
    return m


def test_cache_payload_contains_schema_signature(monkeypatch, tmp_path):
    m = _mgr(monkeypatch, tmp_path)
    m.load_schema()
    with open(sm.CACHE_PATH, encoding="utf-8") as f:
        payload = json.load(f)
    expected = compute_schema_signature(normalize_structure(_SCHEMA))
    assert payload["schema_signature"] == expected


def test_current_schema_signature_matches_pure_helper(monkeypatch, tmp_path):
    m = _mgr(monkeypatch, tmp_path)
    assert m._current_schema_signature() == \
           compute_schema_signature(normalize_structure(_SCHEMA))
