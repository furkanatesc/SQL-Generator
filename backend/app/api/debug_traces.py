import os
from fastapi import APIRouter, Depends, HTTPException, Query

from app.trace.dependencies import get_trace_store
from app.trace.store import TraceStore

router = APIRouter(prefix="/api/debug/traces", tags=["debug-traces"])

def ensure_debug_enabled():
    enabled = os.getenv("NL2SQL_DEBUG_ENDPOINTS_ENABLED", "true").lower()
    if enabled not in {"1", "true", "yes"}:
        raise HTTPException(status_code=404, detail="Not found")


@router.get("")
def list_traces(
    limit: int = Query(default=50, ge=1, le=200),
    store: TraceStore = Depends(get_trace_store),
):
    ensure_debug_enabled()
    traces = store.list_recent(limit=limit)
    return {
        "count": len(traces),
        "traces": [trace.__dict__ for trace in traces],
    }


@router.get("/{trace_id}")
def get_trace(
    trace_id: str,
    store: TraceStore = Depends(get_trace_store),
):
    ensure_debug_enabled()
    trace = store.get(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")

    return trace.__dict__
