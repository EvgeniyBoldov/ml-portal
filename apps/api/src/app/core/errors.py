from __future__ import annotations
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette import status
from typing import Any, Optional, Dict
from .middleware import get_request_id

HTTP_STATUS_TO_CODE = {
    400: "VALIDATION_ERROR",
    401: "INVALID_CREDENTIALS",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "IDEMPOTENCY_REPLAYED",
    413: "PAYLOAD_TOO_LARGE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
    502: "BAD_GATEWAY",
    503: "SERVICE_UNAVAILABLE",
    504: "GATEWAY_TIMEOUT",
}

class APIError(Exception):
    def __init__(self, code: str, message: str, *, http_status: int = 400, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.details = details or {}

def _problem(code: str, message: str, http_status: int) -> Dict[str, Any]:
    return {
        "type": "about:blank",
        "title": message,
        "status": http_status,
        "code": code,
        "detail": message,
        "trace_id": get_request_id() or "",
    }

async def api_error_handler(request: Request, exc: APIError):
    return JSONResponse(status_code=exc.http_status, content=_problem(exc.code, str(exc), exc.http_status), media_type="application/problem+json")

async def fastapi_http_exception_handler(request: Request, exc: HTTPException):
    code = HTTP_STATUS_TO_CODE.get(exc.status_code, "UNKNOWN_ERROR")
    return JSONResponse(status_code=exc.status_code, content=_problem(code, str(exc.detail), exc.status_code), media_type="application/problem+json")

async def unhandled_exception_handler(request: Request, exc: Exception):
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=_problem("INTERNAL", "Internal Server Error", 500), media_type="application/problem+json")

def install_exception_handlers(app):
    from starlette.exceptions import HTTPException as StarletteHTTPException
    app.add_exception_handler(APIError, api_error_handler)
    app.add_exception_handler(HTTPException, fastapi_http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, fastapi_http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
