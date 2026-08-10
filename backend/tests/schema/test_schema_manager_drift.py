"""Opt-in structural drift invalidation in load_schema (Sprint 28.7, Task 4)."""
import json
import app.schema_manager as sm


class _FakeEmbedder:
    builds = {"n": 0}

    class _Client:
        model = "fake_model_v1"

    def __init__(self, *a, **k):
        self.embedding_client = self._Client()

    def build_index(self, schema, api_key=None):
        _FakeEmbedder.builds["n"] += 1
        return {}


class _FakeRAG:
    def index_schema_batch(self, schema):
        pass


def _schema(extra_col=False):
    cols = [{"name": "id", "type": "INTEGER", "primary_key": True, "nullable": False}]
    if extra_col:
        cols.append({"name": "email", "type": "TEXT", "primary_key": False, "nullable": True})
    return {"tables": {"t": {"columns": cols, "foreign_keys": []}},
            "graph": {"nodes": ["t"], "edges": []}}


def _mgr(monkeypatch, tmp_path, auto="1", schema_box=None):
    _FakeEmbedder.builds["n"] = 0
    monkeypatch.setattr(sm, "get_db_connection_params",
                        lambda: {"type": "sqlite", "sqlite_path": ":memory:"})
    monkeypatch.setattr(sm, "CACHE_PATH", str(tmp_path / "schema_cache.json"))
    monkeypatch.setattr(sm, "SchemaEmbeddingIndex", _FakeEmbedder)
    cfg = {"hidden_tables_sqlite": "[]", "hidden_columns_sqlite": "{}",
           "auto_schema_drift_check": auto}
    monkeypatch.setattr("app.database.get_config", lambda k: cfg.get(k))
    monkeypatch.setattr("app.rag_manager.RAGManager", lambda *a, **k: _FakeRAG())
    m = sm.SchemaManager()
    box = schema_box if schema_box is not None else {"s": _schema()}
    monkeypatch.setattr(m, "extract_schema_metadata", lambda: dict(box["s"]))
    return m, box


def test_drift_on_reextracts_when_structure_changes(monkeypatch, tmp_path):
    m, box = _mgr(monkeypatch, tmp_path, auto="1")
    m.load_schema()
    assert _FakeEmbedder.builds["n"] == 1        # initial build
    box["s"] = _schema(extra_col=True)           # DB structure drifts
    m.load_schema()
    assert _FakeEmbedder.builds["n"] == 2        # rebuilt due to drift


def test_drift_on_no_change_uses_cache(monkeypatch, tmp_path):
    m, box = _mgr(monkeypatch, tmp_path, auto="1")
    m.load_schema()
    assert _FakeEmbedder.builds["n"] == 1
    m.load_schema()                              # same structure
    assert _FakeEmbedder.builds["n"] == 1        # NOT rebuilt


def test_drift_off_ignores_structure_change(monkeypatch, tmp_path):
    m, box = _mgr(monkeypatch, tmp_path, auto="0")
    m.load_schema()
    assert _FakeEmbedder.builds["n"] == 1
    box["s"] = _schema(extra_col=True)           # structure drifts but check is OFF
    m.load_schema()
    assert _FakeEmbedder.builds["n"] == 1        # cache still used (28.6 semantics)


def test_legacy_cache_without_signature_reextracts_when_on(monkeypatch, tmp_path):
    m, box = _mgr(monkeypatch, tmp_path, auto="1")
    m.load_schema()                              # writes fingerprint + signature
    # strip the signature to simulate a pre-28.7 cache but keep fingerprint valid
    with open(sm.CACHE_PATH, encoding="utf-8") as f:
        data = json.load(f)
    data.pop("schema_signature", None)
    with open(sm.CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f)
    _FakeEmbedder.builds["n"] = 0
    m.load_schema()
    assert _FakeEmbedder.builds["n"] == 1        # missing signature -> treated as drift
