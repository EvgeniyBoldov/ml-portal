from __future__ import annotations
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi import status
from typing import Any, Optional, Dict
from .request_id import get_request_id

class APIError(Exception):
    def __init__(self, code: str, message: str, *, http_status: int = 400, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.details = details or {}

def format_error_payload(code: str, message: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return {
        "error": {"code": code, "message": message, "details": details or {}},
        "request_id": get_request_id(),
    }

async def http_exception_handler(request: Request, exc: APIError):
    payload = format_error_payload(exc.code, str(exc), exc.details)
    return JSONResponse(status_code=exc.http_status, content=payload)

async def unhandled_exception_handler(request: Request, exc: Exception):
    payload = format_error_payload("internal_error", "Internal Server Error")
    return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=payload)

def install_exception_handlers(app):
    from fastapi import HTTPException
    app.add_exception_handler(APIError, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
