from app.schema_reindex import reindex_embeddings, ReindexReport
from app.schema.reindex_planner import build_table_embedding_text, compute_embedding_fingerprint


class _FakeEmbedder:
    def __init__(self):
        self.embedded_batches = []   # list of table-name lists build_index was called with

    def build_index(self, schema, api_key=None):
        names = list(schema.get("tables", {}).keys())
        self.embedded_batches.append(names)
        return {n: [float(len(n))] for n in names}   # deterministic fake vector


class _FakeRAG:
    def __init__(self):
        self.deleted = []

    def delete_schema_points(self, names):
        self.deleted.extend(names)
        return len(names)


def _meta(cols):
    return {"columns": [{"name": n, "type": t} for (n, t) in cols], "foreign_keys": []}


def _schema(tables):
    return {"tables": tables, "graph": {"nodes": [], "edges": []}}


def _emb_of(schema, model):
    return {"model": model, "tables": {n: [float(len(n))] for n in schema["tables"]},
            "fingerprints": {n: compute_embedding_fingerprint(
                build_table_embedding_text(n, schema["tables"][n]), model)
                for n in schema["tables"]}}


def test_only_changed_and_new_are_embedded():
    old_schema = _schema({"users": _meta([("id", "INTEGER")]),
                          "orders": _meta([("id", "INTEGER")])})
    old = _emb_of(old_schema, "m")
    # users unchanged, orders changed (new column), products new, accounts removed
    old["fingerprints"]["accounts"] = "stale"
    old["tables"]["accounts"] = [9.0]
    new_schema = _schema({"users": _meta([("id", "INTEGER")]),
                          "orders": _meta([("id", "INTEGER"), ("total", "REAL")]),
                          "products": _meta([("id", "INTEGER")])})
    emb = _FakeEmbedder(); rag = _FakeRAG()
    new_emb, report = reindex_embeddings(old_embeddings=old, new_schema=new_schema,
                                         model="m", embedder=emb, rag=rag)
    # only orders + products embedded (users kept)
    assert sorted(sum(emb.embedded_batches, [])) == ["orders", "products"]
    assert report.embedded == ("orders", "products")
    assert report.kept == 1                      # users
    assert "users" in new_emb["tables"]          # kept vector reused
    assert new_emb["tables"]["users"] == old["tables"]["users"]
    assert set(new_emb["tables"].keys()) == {"users", "orders", "products"}
    assert "accounts" in report.deleted          # removed table evicted
    assert "accounts" in rag.deleted
    # fingerprints present for all current tables
    assert set(new_emb["fingerprints"].keys()) == {"users", "orders", "products"}


def test_force_re_embeds_all():
    sch = _schema({"users": _meta([("id", "INTEGER")])})
    old = _emb_of(sch, "m")
    emb = _FakeEmbedder()
    new_emb, report = reindex_embeddings(old_embeddings=old, new_schema=sch, model="m",
                                         embedder=emb, rag=None, force=True)
    assert report.embedded == ("users",)
    assert report.kept == 0


def test_legacy_none_embeddings_embeds_all():
    sch = _schema({"users": _meta([("id", "INTEGER")]), "orders": _meta([("id", "INTEGER")])})
    emb = _FakeEmbedder()
    new_emb, report = reindex_embeddings(old_embeddings=None, new_schema=sch, model="m",
                                         embedder=emb, rag=None)
    assert set(report.embedded) == {"users", "orders"}
    assert report.kept == 0


def test_to_keep_without_cached_vector_is_re_embedded():
    # fingerprint matches (to_keep) but old vector missing -> must re-embed, not drop
    sch = _schema({"users": _meta([("id", "INTEGER")])})
    fp = compute_embedding_fingerprint(build_table_embedding_text("users", sch["tables"]["users"]), "m")
    old = {"model": "m", "tables": {}, "fingerprints": {"users": fp}}  # no vector
    emb = _FakeEmbedder()
    new_emb, report = reindex_embeddings(old_embeddings=old, new_schema=sch, model="m",
                                         embedder=emb, rag=None)
    assert "users" in new_emb["tables"]
    assert "users" in sum(emb.embedded_batches, [])
