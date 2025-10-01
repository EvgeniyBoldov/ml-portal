from __future__ import annotations
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi import status
from typing import Any, Optional, Dict
from app.core.middleware import get_request_id
from app.schemas.common import Problem

# Unified HTTP status to error code mapping
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
    504: "GATEWAY_TIMEOUT"
}

class APIError(Exception):
    def __init__(self, code: str, message: str, *, http_status: int = 400, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.details = details or {}

def format_problem_payload(code: str, message: str, http_status: int, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Format error as RFC7807 Problem"""
    return {
        "type": "about:blank",
        "title": message,
        "status": http_status,
        "code": code,
        "detail": message,
        "trace_id": get_request_id()
    }

def format_error_payload(code: str, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Legacy error format (deprecated)"""
    return {
        "error": {"code": code, "message": message, "details": details or {}},
        "request_id": get_request_id(),
    }

async def http_exception_handler(request: Request, exc: APIError):
    payload = format_problem_payload(exc.code, str(exc), exc.http_status, exc.details)
    return JSONResponse(
        status_code=exc.http_status, 
        content=payload,
        headers={"Content-Type": "application/problem+json"}
    )

async def fastapi_http_exception_handler(request: Request, exc: HTTPException):
    """Handle FastAPI HTTPException with Problem format"""
    error_code = HTTP_STATUS_TO_CODE.get(exc.status_code, "UNKNOWN_ERROR")
    
    payload = format_problem_payload(
        code=error_code,
        message=exc.detail,
        http_status=exc.status_code
    )
    return JSONResponse(
        status_code=exc.status_code, 
        content=payload,
        headers={"Content-Type": "application/problem+json"}
    )

async def unhandled_exception_handler(request: Request, exc: Exception):
    payload = format_problem_payload(
        code="INTERNAL",
        message="Internal Server Error",
        http_status=status.HTTP_500_INTERNAL_SERVER_ERROR
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
        content=payload,
        headers={"Content-Type": "application/problem+json"}
    )

async def starlette_exception_handler(request: Request, exc: Exception):
    """Handle Starlette exceptions with Problem format"""
    from starlette.exceptions import HTTPException as StarletteHTTPException
    
    if isinstance(exc, StarletteHTTPException):
        error_code = HTTP_STATUS_TO_CODE.get(exc.status_code, "UNKNOWN_ERROR")
        
        payload = format_problem_payload(
            code=error_code,
            message=exc.detail,
            http_status=exc.status_code
        )
        return JSONResponse(
            status_code=exc.status_code, 
            content=payload,
            headers={"Content-Type": "application/problem+json"}
        )
    
    # Fallback to unhandled exception handler
    return await unhandled_exception_handler(request, exc)

def install_exception_handlers(app):
    """Install all exception handlers"""
    from starlette.exceptions import HTTPException as StarletteHTTPException
    
    app.add_exception_handler(APIError, http_exception_handler)
    app.add_exception_handler(HTTPException, fastapi_http_exception_handler)
    app.add_exception_handler(StarletteHTTPException, starlette_exception_handler)
    app.add_exception_handler(Exception, starlette_exception_handler)
