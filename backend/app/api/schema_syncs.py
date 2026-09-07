"""Schema Sync API (Sprint 30.3).

/api/v1/schema-syncs — per-connection schema snapshots + structural drift on the
30.0 contract. Inert: the schema is provided in the request (no live
introspection). Protected by verify_api_key.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.api.contract import API_V1_PREFIX, ApiResponse, PageMeta, ResponseMeta
from app.auth import verify_api_key
from app import schema_sync_repository as repo
from app import connection_repository as conn_repo

router = APIRouter(
    prefix=f"{API_V1_PREFIX}/schema-syncs",
    tags=["schema-syncs"],
    dependencies=[Depends(verify_api_key)],
)


class SchemaSyncCreate(BaseModel):
    # `structure` (not `schema`): avoids shadowing BaseModel.schema, and mirrors
    # SchemaSyncResponse.structure so the request/response field name is symmetric.
    connection_id: str
    structure: dict


class SchemaSyncResponse(BaseModel):
    id: str
    connection_id: str
    signature: str
    previous_signature: Optional[str] = None
    drifted: bool
    drift: dict
    structure: dict
    created_at: str


def _resp(row) -> ApiResponse[SchemaSyncResponse]:
    return ApiResponse[SchemaSyncResponse](data=SchemaSyncResponse(**repo.row_to_response_dict(row)))


@router.post("", status_code=201, response_model=ApiResponse[SchemaSyncResponse])
def create_schema_sync(payload: SchemaSyncCreate) -> ApiResponse[SchemaSyncResponse]:
    if conn_repo.get_connection(payload.connection_id) is None:
        raise HTTPException(status_code=400, detail="connection_id mevcut değil")
    try:
        row = repo.create_schema_sync(payload.connection_id, payload.structure)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _resp(row)


@router.get("", response_model=ApiResponse[list[SchemaSyncResponse]])
def list_schema_syncs(
    connection_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ApiResponse[list[SchemaSyncResponse]]:
    rows = repo.list_schema_syncs(limit=limit, offset=offset, connection_id=connection_id)
    data = [SchemaSyncResponse(**repo.row_to_response_dict(r)) for r in rows]
    meta = ResponseMeta(pagination=PageMeta(limit=limit, offset=offset, count=len(data)))
    return ApiResponse[list[SchemaSyncResponse]](data=data, meta=meta)


@router.get("/{sync_id}", response_model=ApiResponse[SchemaSyncResponse])
def get_schema_sync(sync_id: str) -> ApiResponse[SchemaSyncResponse]:
    row = repo.get_schema_sync(sync_id)
    if row is None:
        raise HTTPException(status_code=404, detail="schema-sync bulunamadı")
    return _resp(row)


@router.delete("/{sync_id}", response_model=ApiResponse[SchemaSyncResponse])
def delete_schema_sync(sync_id: str) -> ApiResponse[SchemaSyncResponse]:
    row = repo.get_schema_sync(sync_id)
    if row is None:
        raise HTTPException(status_code=404, detail="schema-sync bulunamadı")
    if not repo.delete_schema_sync(sync_id):
        raise HTTPException(status_code=404, detail="schema-sync bulunamadı")
    return _resp(row)
