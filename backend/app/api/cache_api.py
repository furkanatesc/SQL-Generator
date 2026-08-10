"""Result-cache debug router (Sprint 28.9).

GET  /api/debug/cache/stats  - entry + total-hit counts (read-only).
POST /api/debug/cache/clear  - empty the sql_cache, return deleted count.

Follows the metrics_api/schema_sync_api pattern: own APIRouter, verify_api_key
dependency, per-handler ensure_debug_enabled() -> 404 when debug is disabled.
"""
from fastapi import APIRouter, Depends, HTTPException

from app.api.schemas import CacheClearEnvelopeResponse, CacheStatsEnvelopeResponse
from app.auth import verify_api_key
from app.result_cache import cache_stats, clear_cache
from app.settings import get_settings

router = APIRouter(
    prefix="/api/debug/cache",
    tags=["debug-cache"],
    dependencies=[Depends(verify_api_key)],
)


def ensure_debug_enabled():
    if not get_settings().debug_endpoints_enabled:
        raise HTTPException(status_code=404, detail="Not found")


@router.get("/stats", response_model=CacheStatsEnvelopeResponse)
def cache_stats_endpoint():
    ensure_debug_enabled()
    stats = cache_stats()
    return {"status": "success", "entries": stats["entries"], "total_hits": stats["total_hits"]}


@router.post("/clear", response_model=CacheClearEnvelopeResponse)
def cache_clear_endpoint():
    ensure_debug_enabled()
    return {"status": "success", "deleted": clear_cache()}
