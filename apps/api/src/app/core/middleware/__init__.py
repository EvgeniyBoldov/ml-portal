from __future__ import annotations
import uuid
from typing import Optional
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

_REQUEST_ID_CTX_KEY = "request_id"

def get_request_id(request: Optional[Request] = None) -> str | None:
    if request and hasattr(request.state, _REQUEST_ID_CTX_KEY):
        return getattr(request.state, _REQUEST_ID_CTX_KEY)
    return None

class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        request.state.tenant_id = request.headers.get("X-Tenant-Id")
        response = await call_next(request)
        response.headers["X-Request-Id"] = request.state.request_id
        return response
