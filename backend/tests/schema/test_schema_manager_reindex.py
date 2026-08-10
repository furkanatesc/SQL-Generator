"""load_schema uses granular re-index on rebuild (Sprint 28.8, Task 5)."""
import app.schema_manager as sm


class _FakeEmbedder:
    calls = {"embedded": []}   # flat list of table names embedded across build_index calls

    class _Client:
        model = "fake_model_v1"

    def __init__(self, *a, **k):
        self.embedding_client = self._Client()

    def build_index(self, schema, api_key=None):
        names = list(schema.get("tables", {}).keys())
        _FakeEmbedder.calls["embedded"].extend(names)
        return {n: [float(len(n))] for n in names}


class _FakeRAG:
    deleted = []
    pruned_calls = []   # list of `valid` sets passed to prune_schema_ddl_points

    def index_schema_batch(self, schema):
        pass

    def delete_schema_points(self, names):
        _FakeRAG.deleted.extend(names)
        return len(names)

    def prune_schema_ddl_points(self, valid):
        _FakeRAG.pruned_calls.append(set(valid))
        return []


def _schema(tables):
    return {"tables": {t: {"columns": cols, "foreign_keys": []} for t, cols in tables.items()},
            "graph": {"nodes": list(tables), "edges": []}}


def _mgr(monkeypatch, tmp_path, box):
    _FakeEmbedder.calls["embedded"] = []
    _FakeRAG.deleted = []
    _FakeRAG.pruned_calls = []
    monkeypatch.setattr(sm, "get_db_connection_params",
                        lambda: {"type": "sqlite", "sqlite_path": ":memory:"})
    monkeypatch.setattr(sm, "CACHE_PATH", str(tmp_path / "schema_cache.json"))
    monkeypatch.setattr(sm, "SchemaEmbeddingIndex", _FakeEmbedder)
    monkeypatch.setattr("app.database.get_config",
                        lambda k: {"hidden_tables_sqlite": "[]", "hidden_columns_sqlite": "{}",
                                   "auto_schema_drift_check": "1"}.get(k))
    monkeypatch.setattr("app.rag_manager.RAGManager", lambda *a, **k: _FakeRAG())
    m = sm.SchemaManager()
    monkeypatch.setattr(m, "extract_schema_metadata", lambda: _copy(box["s"]))
    return m


def _copy(s):
    import copy
    return copy.deepcopy(s)


def test_rebuild_reembeds_only_changed_table(monkeypatch, tmp_path):
    box = {"s": _schema({"users": [{"name": "id", "type": "INTEGER"}],
                         "orders": [{"name": "id", "type": "INTEGER"}]})}
    m = _mgr(monkeypatch, tmp_path, box)
    m.load_schema()                                   # first build: both embedded
    assert sorted(_FakeEmbedder.calls["embedded"]) == ["orders", "users"]
    _FakeEmbedder.calls["embedded"] = []
    # change only orders -> structural drift (auto_schema_drift_check on) -> rebuild
    box["s"]["tables"]["orders"]["columns"].append({"name": "total", "type": "REAL"})
    m.load_schema()
    assert _FakeEmbedder.calls["embedded"] == ["orders"]   # ONLY orders re-embedded


def test_removed_table_is_evicted(monkeypatch, tmp_path):
    box = {"s": _schema({"users": [{"name": "id", "type": "INTEGER"}],
                         "orders": [{"name": "id", "type": "INTEGER"}]})}
    m = _mgr(monkeypatch, tmp_path, box)
    m.load_schema()
    del box["s"]["tables"]["orders"]                  # remove a table
    box["s"]["graph"]["nodes"] = ["users"]
    m.load_schema()
    assert "orders" in _FakeRAG.deleted
    # prune-on-rebuild (Fix 1): the rebuild also prunes schema_ddl against the
    # freshly built table set, so "orders" must be absent from the valid set passed.
    assert _FakeRAG.pruned_calls, "prune_schema_ddl_points was not called on rebuild"
    assert "orders" not in _FakeRAG.pruned_calls[-1]
    assert _FakeRAG.pruned_calls[-1] == {"users"}


def test_force_refresh_reembeds_all(monkeypatch, tmp_path):
    box = {"s": _schema({"users": [{"name": "id", "type": "INTEGER"}],
                         "orders": [{"name": "id", "type": "INTEGER"}]})}
    m = _mgr(monkeypatch, tmp_path, box)
    m.load_schema()
    _FakeEmbedder.calls["embedded"] = []
    m.load_schema(force_refresh=True)
    assert sorted(_FakeEmbedder.calls["embedded"]) == ["orders", "users"]


def test_cache_embeddings_has_fingerprints(monkeypatch, tmp_path):
    import json
    box = {"s": _schema({"users": [{"name": "id", "type": "INTEGER"}]})}
    m = _mgr(monkeypatch, tmp_path, box)
    m.load_schema()
    with open(sm.CACHE_PATH, encoding="utf-8") as f:
        payload = json.load(f)
    assert "fingerprints" in payload["embeddings"]
    assert "users" in payload["embeddings"]["fingerprints"]
