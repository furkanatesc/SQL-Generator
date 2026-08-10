import json
import pytest
from fastapi.testclient import TestClient

import app.api.schema_sync_api as api
from app.main import app
from app.schema.reindex_planner import build_table_embedding_text, compute_embedding_fingerprint

client = TestClient(app)
HEADERS = {"X-API-Key": "sqlgen_secret_dev_key"}


def _schema(tables):
    return {"tables": {t: {"columns": [{"name": "id", "type": "INTEGER"}], "foreign_keys": []}
                       for t in tables},
            "graph": {"nodes": list(tables), "edges": []}}


def _cache(tables, model, *, drift_table=None):
    sch = _schema(tables)
    fps = {t: compute_embedding_fingerprint(build_table_embedding_text(t, sch["tables"][t]), model)
           for t in tables}
    if drift_table:                                  # simulate a stale fingerprint
        fps[drift_table] = "stale"
    return {"schema": sch, "cache_fingerprint": "FP", "schema_signature": "SIG",
            "embeddings": {"model": model, "tables": {t: [1.0] for t in tables}, "fingerprints": fps}}


class _FakeEmbedder:
    class _Client:
        model = "m"

    def __init__(self, *a, **k):
        self.embedding_client = self._Client()

    def build_index(self, schema, api_key=None):
        return {n: [2.0] for n in schema.get("tables", {})}


class _FakeRAG:
    def __init__(self):
        self.pruned = []
        self.indexed = False

    def audit_schema_ddl_points(self, valid):
        return {"orphaned": ["ghost"], "stale_id": [], "total": len(valid) + 1}

    def prune_schema_ddl_points(self, valid):
        self.pruned.append(set(valid))
        return ["ghost"]

    def delete_schema_points(self, names):
        return len(names)

    def index_schema_batch(self, schema):
        self.indexed = True


@pytest.fixture
def wire(monkeypatch, tmp_path):
    def _install(*, cache, model="m"):
        p = tmp_path / "schema_cache.json"
        if cache is not None:
            p.write_text(json.dumps(cache), encoding="utf-8")
        monkeypatch.setattr(api, "CACHE_PATH", str(p))
        monkeypatch.setattr(api, "SchemaManager", lambda: object())
        monkeypatch.setattr(api, "SchemaEmbeddingIndex", _FakeEmbedder)
        rag = _FakeRAG()
        monkeypatch.setattr(api, "RAGManager", lambda *a, **k: rag)
        monkeypatch.setattr(api, "compute_cache_fingerprint", lambda **k: "NEWFP")
        return rag, p
    return _install


def test_status_reports_stale_and_orphaned(wire):
    wire(cache=_cache(["users", "orders"], "m", drift_table="orders"))
    r = client.get("/api/debug/schema/reindex-status", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert "orders" in body["stale"]
    assert "ghost" in body["orphaned_qdrant"]
    assert body["model"] == "m"


def test_status_is_read_only_404_when_disabled(wire, monkeypatch):
    wire(cache=_cache(["users"], "m"))
    class _Off:
        debug_endpoints_enabled = False
    monkeypatch.setattr(api, "get_settings", lambda: _Off())
    assert client.get("/api/debug/schema/reindex-status", headers=HEADERS).status_code == 404


def test_reindex_embeds_stale_and_writes_cache(wire):
    rag, path = wire(cache=_cache(["users", "orders"], "m", drift_table="orders"))
    r = client.post("/api/debug/schema/reindex", headers=HEADERS)
    assert r.status_code == 200
    body = r.json()
    assert "orders" in body["embedded"]
    assert rag.indexed is True                        # upsert via index_schema_batch
    # cache embeddings rewritten with a fresh fingerprint for orders; schema preserved
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert set(payload["schema"]["tables"]) == {"users", "orders"}
    assert payload["cache_fingerprint"] == "NEWFP"
    assert payload["embeddings"]["fingerprints"]["orders"] != "stale"


def test_reindex_requires_api_key(wire):
    wire(cache=_cache(["users"], "m"))
    assert client.post("/api/debug/schema/reindex").status_code == 403


def test_reindex_404_when_disabled(wire, monkeypatch):
    wire(cache=_cache(["users"], "m"))
    class _Off:
        debug_endpoints_enabled = False
    monkeypatch.setattr(api, "get_settings", lambda: _Off())
    assert client.post("/api/debug/schema/reindex", headers=HEADERS).status_code == 404
