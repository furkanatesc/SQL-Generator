"""Workspace CRUD API (Sprint 30.1).

/api/v1/workspaces — the first resource built on the 30.0 canonical API
contract (ApiResponse envelope + offset PageMeta). Protected by verify_api_key.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from app.api.contract import API_V1_PREFIX, ApiResponse, PageMeta, ResponseMeta
from app.auth import verify_api_key
from app import workspace_repository as repo

router = APIRouter(
    prefix=f"{API_V1_PREFIX}/workspaces",
    tags=["workspaces"],
    dependencies=[Depends(verify_api_key)],
)

_SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: Optional[str] = Field(default=None, pattern=_SLUG_PATTERN, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _at_least_one(self):
        if self.name is None and self.description is None:
            raise ValueError("en az bir alan (name/description) verilmelidir")
        return self


class WorkspaceResponse(BaseModel):
    id: str
    name: str
    slug: str
    description: Optional[str] = None
    created_at: str
    updated_at: str


@router.post("", status_code=201, response_model=ApiResponse[WorkspaceResponse])
def create_workspace(payload: WorkspaceCreate) -> ApiResponse[WorkspaceResponse]:
    slug = payload.slug or repo.slugify(payload.name)
    try:
        ws = repo.create_workspace(payload.name, slug, payload.description)
    except repo.WorkspaceSlugConflict:
        raise HTTPException(status_code=409, detail=f"slug '{slug}' zaten kullanımda")
    return ApiResponse[WorkspaceResponse](data=WorkspaceResponse(**ws))


@router.get("", response_model=ApiResponse[list[WorkspaceResponse]])
def list_workspaces(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ApiResponse[list[WorkspaceResponse]]:
    rows = repo.list_workspaces(limit=limit, offset=offset)
    data = [WorkspaceResponse(**r) for r in rows]
    meta = ResponseMeta(pagination=PageMeta(limit=limit, offset=offset, count=len(data)))
    return ApiResponse[list[WorkspaceResponse]](data=data, meta=meta)


@router.get("/{workspace_id}", response_model=ApiResponse[WorkspaceResponse])
def get_workspace(workspace_id: str) -> ApiResponse[WorkspaceResponse]:
    ws = repo.get_workspace(workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="workspace bulunamadı")
    return ApiResponse[WorkspaceResponse](data=WorkspaceResponse(**ws))


@router.patch("/{workspace_id}", response_model=ApiResponse[WorkspaceResponse])
def update_workspace(workspace_id: str, payload: WorkspaceUpdate) -> ApiResponse[WorkspaceResponse]:
    ws = repo.update_workspace(
        workspace_id, name=payload.name, description=payload.description
    )
    if ws is None:
        raise HTTPException(status_code=404, detail="workspace bulunamadı")
    return ApiResponse[WorkspaceResponse](data=WorkspaceResponse(**ws))


@router.delete("/{workspace_id}", response_model=ApiResponse[WorkspaceResponse])
def delete_workspace(workspace_id: str) -> ApiResponse[WorkspaceResponse]:
    ws = repo.get_workspace(workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="workspace bulunamadı")
    # Gate the response on the delete actually removing a row, so a concurrent
    # delete loses with a 404 instead of a stale 200.
    if not repo.delete_workspace(workspace_id):
        raise HTTPException(status_code=404, detail="workspace bulunamadı")
    return ApiResponse[WorkspaceResponse](data=WorkspaceResponse(**ws))
