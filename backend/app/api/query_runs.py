"""Query Run API (Sprint 30.4).

/api/v1/query-runs — an inert ledger of SQL runs against a connection on the
30.0 contract. Records the SQL and an optional provided outcome; opens no live
DB connection and resolves no secret. Protected by verify_api_key.
"""
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.contract import API_V1_PREFIX, ApiResponse, PageMeta, ResponseMeta
from app.auth import verify_api_key
from app import query_run_repository as repo
from app import connection_repository as conn_repo

router = APIRouter(
    prefix=f"{API_V1_PREFIX}/query-runs",
    tags=["query-runs"],
    dependencies=[Depends(verify_api_key)],
)


class QueryRunResult(BaseModel):
    columns: list[str] = []
    rows: list[list[Any]] = []
    truncated: bool = False
    duration_ms: Optional[float] = None


class QueryRunCreate(BaseModel):
    connection_id: str
    sql: str = Field(min_length=1)
    result: Optional[QueryRunResult] = None
    execution_error: Optional[str] = None


class QueryRunResponse(BaseModel):
    id: str
    connection_id: str
    sql: str
    status: str
    row_count: Optional[int] = None
    result: Optional[QueryRunResult] = None
    execution_error: Optional[str] = None
    created_at: str


def _resp(row) -> ApiResponse[QueryRunResponse]:
    return ApiResponse[QueryRunResponse](data=QueryRunResponse(**repo.row_to_response_dict(row)))


@router.post("", status_code=201, response_model=ApiResponse[QueryRunResponse])
def create_query_run(payload: QueryRunCreate) -> ApiResponse[QueryRunResponse]:
    if conn_repo.get_connection(payload.connection_id) is None:
        raise HTTPException(status_code=400, detail="connection_id mevcut değil")
    if payload.execution_error is not None:
        result = {"execution_error": payload.execution_error}
    elif payload.result is not None:
        result = payload.result.model_dump()
    else:
        result = None
    row = repo.create_query_run(payload.connection_id, payload.sql, result=result)
    return _resp(row)


@router.get("", response_model=ApiResponse[list[QueryRunResponse]])
def list_query_runs(
    connection_id: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ApiResponse[list[QueryRunResponse]]:
    rows = repo.list_query_runs(limit=limit, offset=offset, connection_id=connection_id, status=status)
    data = [QueryRunResponse(**repo.row_to_response_dict(r)) for r in rows]
    meta = ResponseMeta(pagination=PageMeta(limit=limit, offset=offset, count=len(data)))
    return ApiResponse[list[QueryRunResponse]](data=data, meta=meta)


@router.get("/{run_id}", response_model=ApiResponse[QueryRunResponse])
def get_query_run(run_id: str) -> ApiResponse[QueryRunResponse]:
    row = repo.get_query_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="query-run bulunamadı")
    return _resp(row)


@router.delete("/{run_id}", response_model=ApiResponse[QueryRunResponse])
def delete_query_run(run_id: str) -> ApiResponse[QueryRunResponse]:
    row = repo.get_query_run(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="query-run bulunamadı")
    if not repo.delete_query_run(run_id):
        raise HTTPException(status_code=404, detail="query-run bulunamadı")
    return _resp(row)
