"""Pure re-index planning for granular schema embedding refresh (Sprint 28.8).

Side-effect-free, stdlib-only. Produces the per-table embed text, a model-aware
fingerprint, a stable Qdrant point id, and a diff-based plan (to_embed/to_keep/to_delete).
schema_embedding imports this module (never the reverse) so the embedded text and
the fingerprinted text share one source.

No I/O, no external imports.
"""
import hashlib
from dataclasses import dataclass

REINDEX_FINGERPRINT_VERSION = "v1"
_UNIT = "\x1f"


def build_table_embedding_text(table_name, table_meta):
    """The text that gets embedded for a table (byte-identical to the pre-28.8
    SchemaEmbeddingIndex._generate_table_fingerprint output)."""
    table_meta = table_meta or {}
    columns = []
    for col in table_meta.get("columns", []) or []:
        col_name = col.get("name", "")
        col_type = col.get("type") or col.get("data_type") or ""
        if col_type:
            columns.append(f"{col_name} ({col_type})")
        else:
            columns.append(col_name)
    fks = []
    for fk in table_meta.get("foreign_keys", []) or []:
        fks.append(f"references {fk.get('referenced_table')}")
    text = f"Table: {table_name} | Columns: {', '.join(columns)}"
    if fks:
        text += f" | Relations: {', '.join(fks)}"
    return text


def compute_embedding_fingerprint(text, model, *, version=REINDEX_FINGERPRINT_VERSION):
    payload = version + _UNIT + (model or "") + _UNIT + text
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def stable_point_id(name):
    """Deterministic Qdrant point id (process/restart-independent)."""
    digest = hashlib.sha256((name or "").encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % (10 ** 12)


@dataclass(frozen=True)
class ReindexPlan:
    to_embed: tuple = ()
    to_keep: tuple = ()
    to_delete: tuple = ()

    def as_dict(self):
        return {"to_embed": list(self.to_embed),
                "to_keep": list(self.to_keep),
                "to_delete": list(self.to_delete)}


def plan_reindex(old_fingerprints, new_schema, model):
    old_fingerprints = old_fingerprints or {}
    tables = (new_schema or {}).get("tables", {}) or {}
    to_embed, to_keep = [], []
    for name in sorted(tables.keys()):
        text = build_table_embedding_text(name, tables[name])
        fp = compute_embedding_fingerprint(text, model)
        if name in old_fingerprints and old_fingerprints[name] == fp:
            to_keep.append(name)
        else:
            to_embed.append(name)
    to_delete = sorted(set(old_fingerprints.keys()) - set(tables.keys()))
    return ReindexPlan(to_embed=tuple(to_embed), to_keep=tuple(to_keep),
                       to_delete=tuple(to_delete))
