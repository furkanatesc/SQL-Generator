"""Granular embedding re-index executor (Sprint 28.8).

Uses the pure ReindexPlan to embed only new/changed tables, reuse unchanged
vectors, and evict removed tables from Qdrant. Output-equivalent to a full
build_index for the same model+schema, at a fraction of the API cost.
"""
from dataclasses import dataclass

from app.schema.reindex_planner import (
    plan_reindex, build_table_embedding_text, compute_embedding_fingerprint,
)


@dataclass(frozen=True)
class ReindexReport:
    embedded: tuple = ()
    kept: int = 0
    deleted: tuple = ()
    model: str = ""

    def as_dict(self):
        return {"embedded": list(self.embedded), "kept": self.kept,
                "deleted": list(self.deleted), "model": self.model}


def reindex_embeddings(*, old_embeddings, new_schema, model, embedder, rag=None, force=False):
    old = old_embeddings or {}
    old_fp = {} if force else (old.get("fingerprints") or {})
    old_tables = old.get("tables") or {}
    tables = (new_schema or {}).get("tables", {}) or {}

    plan = plan_reindex(old_fp, new_schema, model)

    # Defensive: a to_keep table whose cached vector is missing must be re-embedded.
    keep_with_vec = [n for n in plan.to_keep if n in old_tables]
    embed_names = list(plan.to_embed) + [n for n in plan.to_keep if n not in old_tables]

    new_vectors = {}
    if embed_names:
        sub_schema = {"tables": {n: tables[n] for n in embed_names},
                      "graph": {"nodes": [], "edges": []}}
        new_vectors = embedder.build_index(sub_schema) or {}

    merged_tables = {n: old_tables[n] for n in keep_with_vec}
    merged_tables.update(new_vectors)

    fingerprints = {
        n: compute_embedding_fingerprint(build_table_embedding_text(n, tables[n]), model)
        for n in tables
    }
    new_embeddings = {"model": model, "tables": merged_tables, "fingerprints": fingerprints}

    if rag is not None and plan.to_delete:
        rag.delete_schema_points(list(plan.to_delete))

    report = ReindexReport(embedded=tuple(sorted(embed_names)), kept=len(keep_with_vec),
                           deleted=plan.to_delete, model=model)
    return new_embeddings, report
