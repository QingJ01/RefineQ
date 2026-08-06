"""Stable API error responses."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from refineq.storage.json_store import InvalidIdentifierError

_ERROR_CODES = {
    401: "unauthorized",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
    503: "service_unavailable",
}


async def http_exception_handler(
    _request: Request,
    exception: HTTPException,
) -> JSONResponse:
    """Return one predictable envelope for framework and application errors."""

    detail: Any = exception.detail
    if isinstance(detail, dict):
        message = str(detail.get("message", "Request failed"))
        code = str(detail.get("code", "request_error"))
    else:
        message = detail if isinstance(detail, str) else "Request failed"
        code = _ERROR_CODES.get(exception.status_code, "request_error")
    return JSONResponse(
        status_code=exception.status_code,
        content={"error": {"code": code, "message": message}},
        headers=exception.headers,
    )


async def request_validation_exception_handler(
    _request: Request,
    _exception: RequestValidationError,
) -> JSONResponse:
    """Keep validation failures stable without echoing sensitive input."""

    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "validation_error",
                "message": "Request validation failed",
            }
        },
    )


async def invalid_identifier_exception_handler(
    _request: Request,
    _exception: InvalidIdentifierError,
) -> JSONResponse:
    """Reject unsafe path identifiers without exposing filesystem details."""

    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "invalid_identifier",
                "message": "Request identifier is invalid",
            }
        },
    )
