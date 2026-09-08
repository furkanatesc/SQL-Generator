"""Query History API (Sprint 30.5).

/api/v1/query-history — a read-only history / analytics surface over the 30.4
query_runs ledger (joined to connections for workspace scoping). Protected by
verify_api_key. No writes.
"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from app.api.contract import API_V1_PREFIX, ApiResponse, PageMeta, ResponseMeta
from app.auth import verify_api_key
from app import query_history_repository as repo

router = APIRouter(
    prefix=f"{API_V1_PREFIX}/query-history",
    tags=["query-history"],
    dependencies=[Depends(verify_api_key)],
)


class QueryHistoryEntry(BaseModel):
    id: str
    connection_id: str
    workspace_id: Optional[str] = None
    sql: str
    status: str
    row_count: Optional[int] = None
    created_at: str


class QueryHistorySummary(BaseModel):
    total: int
    by_status: dict[str, int]


@router.get("", response_model=ApiResponse[list[QueryHistoryEntry]])
def list_query_history(
    connection_id: Optional[str] = Query(default=None),
    workspace_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    since: Optional[str] = Query(default=None),
    until: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ApiResponse[list[QueryHistoryEntry]]:
    rows = repo.list_history(limit=limit, offset=offset, connection_id=connection_id,
                             workspace_id=workspace_id, status=status, since=since,
                             until=until, q=q)
    data = [QueryHistoryEntry(**r) for r in rows]
    meta = ResponseMeta(pagination=PageMeta(limit=limit, offset=offset, count=len(data)))
    return ApiResponse[list[QueryHistoryEntry]](data=data, meta=meta)


@router.get("/summary", response_model=ApiResponse[QueryHistorySummary])
def query_history_summary(
    connection_id: Optional[str] = Query(default=None),
    workspace_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    since: Optional[str] = Query(default=None),
    until: Optional[str] = Query(default=None),
    q: Optional[str] = Query(default=None),
) -> ApiResponse[QueryHistorySummary]:
    s = repo.summary(connection_id=connection_id, workspace_id=workspace_id,
                     status=status, since=since, until=until, q=q)
    return ApiResponse[QueryHistorySummary](data=QueryHistorySummary(**s))
