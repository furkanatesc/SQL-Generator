from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import verify_api_key
from app.trace.dependencies import get_trace_store
from app.trace.store import TraceStore
from app.trace.query import TraceQuery
from app.trace.debug_api import DebugTraceAdapter

router = APIRouter(
    prefix="/api/debug/traces",
    tags=["debug-traces"],
    dependencies=[Depends(verify_api_key)],
)

from app.settings import get_settings

def ensure_debug_enabled():
    if not get_settings().debug_endpoints_enabled:
        raise HTTPException(status_code=404, detail="Not found")


@router.get("")
def list_traces(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    trace_type: Optional[str] = Query(default=None),
    request_id: Optional[str] = Query(default=None),
    job_id: Optional[str] = Query(default=None),
    dialect: Optional[str] = Query(default=None),
    created_after: Optional[str] = Query(default=None),
    created_before: Optional[str] = Query(default=None),
    sql_valid: Optional[bool] = Query(default=None),
    error_type: Optional[str] = Query(default=None),
    store: TraceStore = Depends(get_trace_store),
):
    ensure_debug_enabled()
    
    query = TraceQuery(
        limit=limit + 1,
        offset=offset,
        trace_type=trace_type,
        request_id=request_id,
        job_id=job_id,
        dialect=dialect,
        created_after=created_after,
        created_before=created_before,
        sql_valid=sql_valid,
        error_type=error_type,
    )

    adapter = DebugTraceAdapter(store)
    rows = adapter.list_traces(query)
    
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
            "trace_type": trace_type,
            "request_id": request_id,
            "job_id": job_id,
            "dialect": dialect,
            "created_after": created_after,
            "created_before": created_before,
            "sql_valid": sql_valid,
            "error_type": error_type,
        },
        "traces": traces,
    }


@router.get("/{trace_id}")
def get_trace(
    trace_id: str,
    store: TraceStore = Depends(get_trace_store),
):
    ensure_debug_enabled()
    adapter = DebugTraceAdapter(store)
    trace_dict = adapter.get_trace(trace_id)
    if trace_dict is None:
        raise HTTPException(status_code=404, detail="Trace not found")

    return trace_dict
