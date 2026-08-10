"""Schema drift / sync / reindex debug router (Sprint 28.7 + 28.8).

GET  /api/debug/schema/drift            - read-only structural drift report (no rebuild).
POST /api/debug/schema/sync             - drift-aware sync (Task 6).
GET  /api/debug/schema/reindex-status   - read-only embedding-staleness report (28.8).
POST /api/debug/schema/reindex          - granular embedding re-index over the cached schema (28.8).

Follows the metrics_api/rule_suggestions_api pattern: own APIRouter, verify_api_key
dependency, per-handler ensure_debug_enabled() -> 404 when debug is disabled.
The drift and reindex-status reports are SIDE-EFFECT-FREE: they read the cache
file (and, for reindex-status, embedding fingerprints) without calling
load_schema (never rebuild).
"""
import json
import os

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.schemas import (
    ReindexEnvelopeResponse, ReindexStatusEnvelopeResponse,
    SchemaDriftEnvelopeResponse, SchemaSyncEnvelopeResponse)
from app.auth import verify_api_key
from app.database import get_config
from app.rag_manager import RAGManager
from app.schema.reindex_planner import plan_reindex
from app.schema.schema_signature import (
    SCHEMA_SIGNATURE_VERSION, compute_schema_signature, diff_structures,
    normalize_structure)
from app.schema_cache_fingerprint import compute_cache_fingerprint
from app.schema_embedding import SchemaEmbeddingIndex
from app.schema_manager import CACHE_PATH, SchemaManager
from app.schema_reindex import reindex_embeddings
from app.settings import get_settings

router = APIRouter(
    prefix="/api/debug/schema",
    tags=["debug-schema-sync"],
    dependencies=[Depends(verify_api_key)],
)


def ensure_debug_enabled():
    if not get_settings().debug_endpoints_enabled:
        raise HTTPException(status_code=404, detail="Not found")


def _read_cache():
    if not os.path.exists(CACHE_PATH):
        return None
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _compute_drift():
    """Return (drifted, cached_signature, current_signature, StructuralDrift)."""
    mgr = SchemaManager()
    current_norm = mgr._current_normalized_structure()
    current_sig = compute_schema_signature(current_norm)

    cache = _read_cache()
    cached_sig = (cache or {}).get("schema_signature")
    old_norm = normalize_structure((cache or {}).get("schema", {})) if cache else {}
    drift = diff_structures(old_norm, current_norm)
    drifted = (cached_sig is None) or (cached_sig != current_sig)
    return drifted, cached_sig, current_sig, drift


@router.get("/drift", response_model=SchemaDriftEnvelopeResponse)
def schema_drift():
    ensure_debug_enabled()
    drifted, cached_sig, current_sig, drift = _compute_drift()
    return {
        "status": "success",
        "drifted": drifted,
        "signature_version": SCHEMA_SIGNATURE_VERSION,
        "cached_signature": cached_sig,
        "current_signature": current_sig,
        "drift": drift.as_dict(),
    }


@router.post("/sync", response_model=SchemaSyncEnvelopeResponse)
def schema_sync(force: bool = Query(default=False)):
    ensure_debug_enabled()
    drifted, cached_sig, current_sig, drift = _compute_drift()
    if drifted or force:
        SchemaManager().load_schema(force_refresh=True)
        action = "rebuilt"
    else:
        action = "up_to_date"
    return {
        "status": "success",
        "action": action,
        "drifted": drifted,
        "signature_version": SCHEMA_SIGNATURE_VERSION,
        "cached_signature": cached_sig,
        "current_signature": current_sig,
        "drift": drift.as_dict(),
    }


def _current_model():
    return SchemaEmbeddingIndex().embedding_client.model


@router.get("/reindex-status", response_model=ReindexStatusEnvelopeResponse)
def reindex_status():
    ensure_debug_enabled()
    cache = _read_cache() or {}
    schema = cache.get("schema") or {"tables": {}}
    old_fp = (cache.get("embeddings") or {}).get("fingerprints") or {}
    model = _current_model()
    plan = plan_reindex(old_fp, schema, model)
    valid = set((schema.get("tables") or {}).keys())
    try:
        audit = RAGManager().audit_schema_ddl_points(valid)
    except Exception:
        audit = {"orphaned": [], "stale_id": []}
    new = [t for t in plan.to_embed if t not in old_fp]
    stale = [t for t in plan.to_embed if t in old_fp]
    return {
        "status": "success", "model": model,
        "fresh": len(plan.to_keep), "stale": stale, "new": new,
        "to_delete": list(plan.to_delete),
        "orphaned_qdrant": sorted(set(audit.get("orphaned", [])) | set(audit.get("stale_id", []))),
    }


@router.post("/reindex", response_model=ReindexEnvelopeResponse)
def reindex(force: bool = Query(default=False)):
    ensure_debug_enabled()
    cache = _read_cache() or {}
    schema = cache.get("schema") or {"tables": {}}
    old_embeddings = cache.get("embeddings")
    model = _current_model()
    embedder = SchemaEmbeddingIndex()
    rag = RAGManager()

    new_embeddings, report = reindex_embeddings(
        old_embeddings=old_embeddings, new_schema=schema, model=model,
        embedder=embedder, rag=rag, force=force)

    # prune orphan/stale Qdrant points, then upsert current via precomputed vectors
    valid = set((schema.get("tables") or {}).keys())
    try:
        pruned = rag.prune_schema_ddl_points(valid)
    except Exception:
        pruned = []
    try:
        rag.index_schema_batch({**schema, "embeddings": new_embeddings})
    except Exception:
        pass

    # persist: only embeddings + refreshed cache_fingerprint (schema/signature preserved)
    if cache:
        db_type = cache.get("db_type") or (get_config("target_db_type") or "sqlite")
        cache["embeddings"] = new_embeddings
        try:
            cache["cache_fingerprint"] = compute_cache_fingerprint(
                db_type=db_type,
                hidden_tables_raw=get_config(f"hidden_tables_{db_type}"),
                hidden_columns_raw=get_config(f"hidden_columns_{db_type}"),
                embedding_model=model,
            )
        except Exception:
            pass
        try:
            with open(CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(cache, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    return {"status": "success", "embedded": list(report.embedded), "kept": report.kept,
            "deleted": list(report.deleted), "pruned": list(pruned), "model": model}
