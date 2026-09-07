"""Connection Registry API (Sprint 30.2).

/api/v1/connections — persistent connection profiles on the 30.0 contract.
Secret-by-reference only (never a raw secret). Protected by verify_api_key.
Standalone: stores profiles, opens no live connection.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator

from app.api.contract import API_V1_PREFIX, ApiResponse, PageMeta, ResponseMeta
from app.auth import verify_api_key
from app import connection_repository as repo
from app import workspace_repository as ws_repo
from app.evaluation.connection_abstraction import (
    SQLConnectionAuthMode,
    SQLConnectionEnvironment,
    SQLConnectionAbstractionContractError,
)
from app.evaluation.multi_database_execution import SQLDatabaseDialect

router = APIRouter(
    prefix=f"{API_V1_PREFIX}/connections",
    tags=["connections"],
    dependencies=[Depends(verify_api_key)],
)

_REF_PATTERN = r"^[a-z0-9]+(-[a-z0-9]+)*$"


class SecretRefModel(BaseModel):
    provider: str = Field(min_length=1, max_length=100)
    key: str = Field(min_length=1, max_length=100)


class EndpointModel(BaseModel):
    host: str
    port: int
    database: str


class ConnectionCreate(BaseModel):
    connection_ref: str = Field(pattern=_REF_PATTERN, max_length=200)
    name: str = Field(min_length=1, max_length=200)
    dialect: SQLDatabaseDialect
    environment: SQLConnectionEnvironment
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    database: str = Field(min_length=1, max_length=255)
    auth_mode: SQLConnectionAuthMode
    secret_ref: Optional[SecretRefModel] = None
    workspace_id: Optional[str] = None
    max_rows: int = Field(default=1000, gt=0)
    timeout_seconds: float = Field(default=2.0, gt=0)


class ConnectionUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    host: Optional[str] = Field(default=None, min_length=1, max_length=255)
    port: Optional[int] = Field(default=None, ge=1, le=65535)
    database: Optional[str] = Field(default=None, min_length=1, max_length=255)
    environment: Optional[SQLConnectionEnvironment] = None
    auth_mode: Optional[SQLConnectionAuthMode] = None
    secret_ref: Optional[SecretRefModel] = None
    max_rows: Optional[int] = Field(default=None, gt=0)
    timeout_seconds: Optional[float] = Field(default=None, gt=0)

    @model_validator(mode="after")
    def _at_least_one(self):
        if all(getattr(self, f) is None for f in (
            "name", "host", "port", "database", "environment",
            "auth_mode", "secret_ref", "max_rows", "timeout_seconds",
        )):
            raise ValueError("en az bir alan verilmelidir")
        return self


class ConnectionResponse(BaseModel):
    id: str
    connection_ref: str
    workspace_id: Optional[str] = None
    name: str
    dialect: str
    environment: str
    endpoint: EndpointModel
    access_mode: str
    auth_mode: str
    secret_ref: Optional[SecretRefModel] = None
    max_rows: int
    timeout_seconds: float
    created_at: str
    updated_at: str


def _resp(row) -> ApiResponse[ConnectionResponse]:
    return ApiResponse[ConnectionResponse](data=ConnectionResponse(**repo.row_to_response_dict(row)))


@router.post("", status_code=201, response_model=ApiResponse[ConnectionResponse])
def create_connection(payload: ConnectionCreate) -> ApiResponse[ConnectionResponse]:
    if payload.workspace_id is not None and ws_repo.get_workspace(payload.workspace_id) is None:
        raise HTTPException(status_code=400, detail="workspace_id mevcut değil")
    sp = payload.secret_ref.provider if payload.secret_ref else None
    sk = payload.secret_ref.key if payload.secret_ref else None
    try:
        row = repo.create_connection(
            connection_ref=payload.connection_ref, workspace_id=payload.workspace_id,
            name=payload.name, dialect=payload.dialect.value,
            environment=payload.environment.value, host=payload.host, port=payload.port,
            database=payload.database, auth_mode=payload.auth_mode.value,
            secret_provider=sp, secret_key=sk, max_rows=payload.max_rows,
            timeout_seconds=payload.timeout_seconds,
        )
    except repo.ConnectionRefConflict:
        raise HTTPException(status_code=409, detail=f"connection_ref '{payload.connection_ref}' zaten kullanımda")
    except SQLConnectionAbstractionContractError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return _resp(row)


@router.get("", response_model=ApiResponse[list[ConnectionResponse]])
def list_connections(
    workspace_id: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ApiResponse[list[ConnectionResponse]]:
    rows = repo.list_connections(limit=limit, offset=offset, workspace_id=workspace_id)
    data = [ConnectionResponse(**repo.row_to_response_dict(r)) for r in rows]
    meta = ResponseMeta(pagination=PageMeta(limit=limit, offset=offset, count=len(data)))
    return ApiResponse[list[ConnectionResponse]](data=data, meta=meta)


@router.get("/{connection_id}", response_model=ApiResponse[ConnectionResponse])
def get_connection(connection_id: str) -> ApiResponse[ConnectionResponse]:
    row = repo.get_connection(connection_id)
    if row is None:
        raise HTTPException(status_code=404, detail="connection bulunamadı")
    return _resp(row)


@router.patch("/{connection_id}", response_model=ApiResponse[ConnectionResponse])
def update_connection(connection_id: str, payload: ConnectionUpdate) -> ApiResponse[ConnectionResponse]:
    # Build the update fields explicitly, converting enums to their string values
    # (avoids relying on model_dump's enum serialization mode).
    fields: dict = {}
    if payload.name is not None:
        fields["name"] = payload.name
    if payload.host is not None:
        fields["host"] = payload.host
    if payload.port is not None:
        fields["port"] = payload.port
    if payload.database is not None:
        fields["database"] = payload.database
    if payload.environment is not None:
        fields["environment"] = payload.environment.value
    if payload.auth_mode is not None:
        fields["auth_mode"] = payload.auth_mode.value
    if payload.secret_ref is not None:
        fields["secret_provider"] = payload.secret_ref.provider
        fields["secret_key"] = payload.secret_ref.key
    if payload.max_rows is not None:
        fields["max_rows"] = payload.max_rows
    if payload.timeout_seconds is not None:
        fields["timeout_seconds"] = payload.timeout_seconds
    try:
        row = repo.update_connection(connection_id, **fields)
    except SQLConnectionAbstractionContractError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if row is None:
        raise HTTPException(status_code=404, detail="connection bulunamadı")
    return _resp(row)


@router.delete("/{connection_id}", response_model=ApiResponse[ConnectionResponse])
def delete_connection(connection_id: str) -> ApiResponse[ConnectionResponse]:
    row = repo.get_connection(connection_id)
    if row is None:
        raise HTTPException(status_code=404, detail="connection bulunamadı")
    if not repo.delete_connection(connection_id):
        raise HTTPException(status_code=404, detail="connection bulunamadı")
    return _resp(row)
