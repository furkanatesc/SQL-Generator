import json
import logging
import uuid
from typing import Any
from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from app.middleware.request_logging import get_sanitized_path

logger = logging.getLogger("app.request_logging")

# HTTP status -> canonical error code vocabulary. Exposed as a module constant
# so the public API contract descriptor (app/api/contract.py) can be checked
# against it for drift (see the conformance guard) instead of hand-copying it.
STATUS_TO_CODE = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    500: "INTERNAL_SERVER_ERROR",
}


def map_status_to_code(status_code: int) -> str:
    return STATUS_TO_CODE.get(status_code, "HTTP_ERROR")


def normalize_message(detail: Any, status_code: int) -> str:
    if isinstance(detail, str):
        return detail
    if status_code == 422:
        return "Request validation failed."
    return "An error occurred."


def normalize_details(detail: Any) -> Any:
    if isinstance(detail, str):
        return None
    return jsonable_encoder(detail)


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    status_code = exc.status_code
    code = map_status_to_code(status_code)
    
    # Handle manual 422 validations that raise HTTPException
    if status_code == 422:
        code = "VALIDATION_ERROR"

    message = normalize_message(exc.detail, status_code)
    details = normalize_details(exc.detail)

    # Corelated error log
    request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
    try:
        path = get_sanitized_path(request)
    except Exception:
        path = str(request.url.path)

    log_data = {
        "event": "http_error",
        "request_id": request_id,
        "path": path,
        "method": request.method,
        "error_type": exc.__class__.__name__,
        "status_code": status_code
    }
    logger.info(json.dumps(log_data))

    response = JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details,
            }
        },
    )
    response.headers["X-Request-ID"] = request_id
    return response


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = jsonable_encoder(exc.errors())
    
    # Corelated validation error log
    request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
    try:
        path = get_sanitized_path(request)
    except Exception:
        path = str(request.url.path)

    log_data = {
        "event": "validation_error",
        "request_id": request_id,
        "path": path,
        "method": request.method,
        "error_type": exc.__class__.__name__,
        "status_code": 422
    }
    logger.info(json.dumps(log_data))

    response = JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed.",
                "details": errors,
            }
        },
    )
    response.headers["X-Request-ID"] = request_id
    return response


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Corelated unhandled exception log
    request_id = getattr(request.state, "request_id", None) or str(uuid.uuid4())
    try:
        path = get_sanitized_path(request)
    except Exception:
        path = str(request.url.path)

    log_data = {
        "event": "unhandled_exception",
        "request_id": request_id,
        "path": path,
        "method": request.method,
        "error_type": exc.__class__.__name__,
        "status_code": 500
    }
    logger.info(json.dumps(log_data))

    response = JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An error occurred.",
                "details": None,
            }
        },
    )
    response.headers["X-Request-ID"] = request_id
    return response
