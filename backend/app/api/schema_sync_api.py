"""Schema drift / sync debug router (Sprint 28.7).

GET  /api/debug/schema/drift  - read-only structural drift report (no rebuild).
POST /api/debug/schema/sync   - drift-aware sync (Task 6).

Follows the metrics_api/rule_suggestions_api pattern: own APIRouter, verify_api_key
dependency, per-handler ensure_debug_enabled() -> 404 when debug is disabled.
The drift report is SIDE-EFFECT-FREE: it reads the cache file and a fresh
structural signature, and never calls load_schema (never rebuilds).
"""
import json
import os

from fastapi import APIRouter, Depends, HTTPException

from app.auth import verify_api_key
from app.schema.schema_signature import (
    SCHEMA_SIGNATURE_VERSION, diff_structures, normalize_structure)
from app.schema_manager import CACHE_PATH, SchemaManager
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
    current_sig = mgr._current_schema_signature()

    cache = _read_cache()
    cached_sig = (cache or {}).get("schema_signature")
    old_norm = normalize_structure((cache or {}).get("schema", {})) if cache else {}
    drift = diff_structures(old_norm, current_norm)
    drifted = (cached_sig is None) or (cached_sig != current_sig)
    return drifted, cached_sig, current_sig, drift


@router.get("/drift", response_model=None)
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
