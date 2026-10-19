"""Organization CRUD API (Sprint 33.0).

/api/v1/organizations — top-level tenant container; workspaces belong to one.
Protected by verify_api_key.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from app.api.contract import API_V1_PREFIX, ApiResponse, PageMeta, ResponseMeta
from app.auth import verify_api_key
from app import organization_repository as repo
from app.workspace_repository import slugify

router = APIRouter(
    prefix=f"{API_V1_PREFIX}/organizations",
    tags=["organizations"],
    dependencies=[Depends(verify_api_key)],
)

_SLUG_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: Optional[str] = Field(default=None, pattern=_SLUG_PATTERN, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)


class OrganizationUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    description: Optional[str] = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _at_least_one(self):
        if self.name is None and self.description is None:
            raise ValueError("en az bir alan (name/description) verilmelidir")
        return self


class OrganizationResponse(BaseModel):
    id: str
    name: str
    slug: str
    description: Optional[str] = None
    created_at: str
    updated_at: str


_NOT_FOUND = "organization bulunamadı"


@router.post("", status_code=201, response_model=ApiResponse[OrganizationResponse])
def create_organization(payload: OrganizationCreate) -> ApiResponse[OrganizationResponse]:
    slug = payload.slug or slugify(payload.name)
    try:
        org = repo.create_organization(payload.name, slug, payload.description)
    except repo.OrganizationSlugConflict:
        raise HTTPException(status_code=409, detail=f"slug '{slug}' zaten kullanımda")
    return ApiResponse[OrganizationResponse](data=OrganizationResponse(**org))


@router.get("", response_model=ApiResponse[list[OrganizationResponse]])
def list_organizations(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ApiResponse[list[OrganizationResponse]]:
    rows = repo.list_organizations(limit=limit, offset=offset)
    data = [OrganizationResponse(**r) for r in rows]
    meta = ResponseMeta(pagination=PageMeta(limit=limit, offset=offset, count=len(data)))
    return ApiResponse[list[OrganizationResponse]](data=data, meta=meta)


@router.get("/{organization_id}", response_model=ApiResponse[OrganizationResponse])
def get_organization(organization_id: str) -> ApiResponse[OrganizationResponse]:
    org = repo.get_organization(organization_id)
    if org is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return ApiResponse[OrganizationResponse](data=OrganizationResponse(**org))


@router.patch("/{organization_id}", response_model=ApiResponse[OrganizationResponse])
def update_organization(
    organization_id: str, payload: OrganizationUpdate
) -> ApiResponse[OrganizationResponse]:
    org = repo.update_organization(
        organization_id, name=payload.name, description=payload.description
    )
    if org is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return ApiResponse[OrganizationResponse](data=OrganizationResponse(**org))


@router.delete("/{organization_id}", response_model=ApiResponse[OrganizationResponse])
def delete_organization(organization_id: str) -> ApiResponse[OrganizationResponse]:
    org = repo.get_organization(organization_id)
    if org is None:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    try:
        deleted = repo.delete_organization(organization_id)
    except repo.DefaultOrganizationProtected:
        raise HTTPException(status_code=409, detail="varsayılan organization silinemez")
    except repo.OrganizationInUse:
        raise HTTPException(
            status_code=409, detail="organization altında workspace var; önce onları silin"
        )
    if not deleted:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    return ApiResponse[OrganizationResponse](data=OrganizationResponse(**org))
