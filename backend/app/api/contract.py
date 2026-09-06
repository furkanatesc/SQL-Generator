"""Canonical public API contract (Sprint 30.0).

Single source of truth for the product-grade `/api/v1` surface:
- `ApiResponse[T]` — the canonical success envelope ({status, data, meta}).
- `PageMeta`/`ResponseMeta` — offset-based pagination metadata.
- `ErrorResponse`/`ErrorBody` — re-exported existing canonical error ({error:{code,message,details}}).
- `API_CONTRACT` + `contract_descriptor()` — declarative descriptor the
  `GET /api/v1` endpoint serves and the conformance guard reads.

Pure module: imports only pydantic/typing/dataclasses + app.api.schemas.
Never imports app.main (so the guard and the app both import it cheaply).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Literal, Optional, TypeVar

from pydantic import BaseModel

from app.api.schemas import ErrorBody, ErrorResponse  # THE canonical error shape

__all__ = [
    "API_VERSION", "API_V1_PREFIX", "REQUEST_ID_HEADER",
    "ApiResponse", "PageMeta", "ResponseMeta",
    "ApiContract", "API_CONTRACT", "contract_descriptor",
    "ErrorResponse", "ErrorBody",
]

API_VERSION: str = "v1"
API_V1_PREFIX: str = "/api/v1"
REQUEST_ID_HEADER: str = "X-Request-ID"

DataT = TypeVar("DataT")


class PageMeta(BaseModel):
    """Offset-based pagination metadata for a single page of results."""
    limit: int
    offset: int
    count: int  # number of items in THIS page's `data`


class ResponseMeta(BaseModel):
    """Cross-cutting response metadata carried in the canonical envelope."""
    pagination: Optional[PageMeta] = None


class ApiResponse(BaseModel, Generic[DataT]):
    """Canonical public success envelope: {status, data, meta}."""
    status: Literal["success"] = "success"
    data: DataT
    meta: Optional[ResponseMeta] = None


# The HTTP status->code vocabulary emitted by app/api/errors.py handlers.
_REQUIRED_ERROR_CODES: tuple[str, ...] = (
    "BAD_REQUEST", "UNAUTHORIZED", "FORBIDDEN",
    "NOT_FOUND", "VALIDATION_ERROR", "INTERNAL_SERVER_ERROR",
)


@dataclass(frozen=True)
class ApiContract:
    version: str
    prefix: str
    request_id_header: str
    success_envelope_fields: tuple[str, ...]
    error_envelope_shape: dict  # {"error": ("code", "message", "details")}
    pagination_fields: tuple[str, ...]
    required_error_codes: tuple[str, ...]


API_CONTRACT = ApiContract(
    version=API_VERSION,
    prefix=API_V1_PREFIX,
    request_id_header=REQUEST_ID_HEADER,
    success_envelope_fields=tuple(ApiResponse.model_fields.keys()),
    error_envelope_shape={"error": tuple(ErrorBody.model_fields.keys())},
    pagination_fields=tuple(PageMeta.model_fields.keys()),
    required_error_codes=_REQUIRED_ERROR_CODES,
)


def contract_descriptor() -> dict:
    """Render `API_CONTRACT` as a JSON-serializable discovery document."""
    return {
        "version": API_CONTRACT.version,
        "prefix": API_CONTRACT.prefix,
        "request_id_header": API_CONTRACT.request_id_header,
        "success_envelope_fields": list(API_CONTRACT.success_envelope_fields),
        "pagination_fields": list(API_CONTRACT.pagination_fields),
        "error_envelope": {
            "error": list(API_CONTRACT.error_envelope_shape["error"]),
        },
        "required_error_codes": list(API_CONTRACT.required_error_codes),
    }
