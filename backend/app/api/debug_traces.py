import os
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import verify_api_key
from app.trace.dependencies import get_trace_store
from app.trace.store import TraceStore
from app.trace.query import TraceQuery

router = APIRouter(
    prefix="/api/debug/traces",
    tags=["debug-traces"],
    dependencies=[Depends(verify_api_key)],
)

def ensure_debug_enabled():
    enabled = os.getenv("NL2SQL_DEBUG_ENDPOINTS_ENABLED", "true").lower()
    if enabled not in {"1", "true", "yes"}:
        raise HTTPException(status_code=404, detail="Not found")


@router.get("")
def list_traces(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    sql_valid: Optional[bool] = Query(default=None),
    error_type: Optional[str] = Query(default=None),
    job_id: Optional[str] = Query(default=None),
    dialect: Optional[str] = Query(default=None),
    created_after: Optional[str] = Query(default=None),
    created_before: Optional[str] = Query(default=None),
    store: TraceStore = Depends(get_trace_store),
):
    ensure_debug_enabled()
    
    query = TraceQuery(
        limit=limit + 1,
        offset=offset,
        sql_valid=sql_valid,
        error_type=error_type,
        job_id=job_id,
        dialect=dialect,
        created_after=created_after,
        created_before=created_before,
    )

    if hasattr(store, "list_traces_legacy"):
        rows = store.list_traces_legacy(query)
    else:
        rows = store.list_traces(query)
    has_more = len(rows) > limit
    traces = rows[:limit]

    return {
        "count": len(traces),
        "pagination": {
            "limit": limit,
            "offset": offset,
            "next_offset": offset + limit if has_more else None,
            "has_more": has_more,
        },
        "filters": {
            "sql_valid": sql_valid,
            "error_type": error_type,
            "job_id": job_id,
            "dialect": dialect,
            "created_after": created_after,
            "created_before": created_before,
        },
        "traces": [trace.__dict__ for trace in traces],
    }


@router.get("/{trace_id}")
def get_trace(
    trace_id: str,
    store: TraceStore = Depends(get_trace_store),
):
    ensure_debug_enabled()
    if hasattr(store, "get_legacy"):
        trace = store.get_legacy(trace_id)
    else:
        trace = store.get(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail="Trace not found")

    return trace.__dict__
