from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from typing import Any


def map_status_to_code(status_code: int) -> str:
    mapping = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        422: "VALIDATION_ERROR",
        500: "INTERNAL_SERVER_ERROR",
    }
    return mapping.get(status_code, "HTTP_ERROR")


def normalize_message(detail: Any, status_code: int) -> str:
    if isinstance(detail, str):
        return detail
    if status_code == 422:
        return "Request validation failed."
    return "An error occurred."


def normalize_details(detail: Any) -> Any:
    if isinstance(detail, str):
        return None
    return detail


async def http_exception_handler(request: Any, exc: HTTPException) -> JSONResponse:
    status_code = exc.status_code
    code = map_status_to_code(status_code)
    
    # Handle manual 422 validations that raise HTTPException
    if status_code == 422:
        code = "VALIDATION_ERROR"

    message = normalize_message(exc.detail, status_code)
    details = normalize_details(exc.detail)

    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details,
            }
        },
    )


async def validation_exception_handler(request: Any, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed.",
                "details": errors,
            }
        },
    )
