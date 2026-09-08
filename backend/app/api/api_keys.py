"""API Key Management API (Sprint 30.8 — Phase 11 AuthN).

/api/v1/api-keys — managed, hashed, multiple API keys on the 30.0 contract.
The raw key is returned ONLY by POST create; list/detail/revoke expose metadata
only. Protected by the EXISTING verify_api_key (single config key); the new keys
do not yet govern authentication (inert — live enforcement deferred).
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.contract import API_V1_PREFIX, ApiResponse, PageMeta, ResponseMeta
from app.auth import verify_api_key
from app import api_key_repository as repo

router = APIRouter(
    prefix=f"{API_V1_PREFIX}/api-keys",
    tags=["api-keys"],
    dependencies=[Depends(verify_api_key)],
)


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)


class ApiKeyResponse(BaseModel):
    id: str
    name: str
    key_prefix: str
    created_at: str
    revoked_at: Optional[str] = None
    active: bool


class ApiKeyCreated(ApiKeyResponse):
    api_key: str  # the raw key, returned ONCE at creation only


@router.post("", status_code=201, response_model=ApiResponse[ApiKeyCreated])
def create_api_key(payload: ApiKeyCreate) -> ApiResponse[ApiKeyCreated]:
    raw, row = repo.generate_and_create(payload.name)
    data = ApiKeyCreated(api_key=raw, **repo.row_to_response_dict(row))
    return ApiResponse[ApiKeyCreated](data=data)


@router.get("", response_model=ApiResponse[list[ApiKeyResponse]])
def list_api_keys(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ApiResponse[list[ApiKeyResponse]]:
    rows = repo.list_api_keys(limit=limit, offset=offset)
    data = [ApiKeyResponse(**repo.row_to_response_dict(r)) for r in rows]
    meta = ResponseMeta(pagination=PageMeta(limit=limit, offset=offset, count=len(data)))
    return ApiResponse[list[ApiKeyResponse]](data=data, meta=meta)


@router.get("/{key_id}", response_model=ApiResponse[ApiKeyResponse])
def get_api_key(key_id: str) -> ApiResponse[ApiKeyResponse]:
    row = repo.get_api_key(key_id)
    if row is None:
        raise HTTPException(status_code=404, detail="api-key bulunamadı")
    return ApiResponse[ApiKeyResponse](data=ApiKeyResponse(**repo.row_to_response_dict(row)))


@router.post("/{key_id}/revoke", response_model=ApiResponse[ApiKeyResponse])
def revoke_api_key(key_id: str) -> ApiResponse[ApiKeyResponse]:
    row = repo.revoke_api_key(key_id)
    if row is None:
        raise HTTPException(status_code=404, detail="api-key bulunamadı")
    return ApiResponse[ApiKeyResponse](data=ApiKeyResponse(**repo.row_to_response_dict(row)))
