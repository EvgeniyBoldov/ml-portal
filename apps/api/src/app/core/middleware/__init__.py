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

class TenantMiddleware(BaseHTTPMiddleware):
    """Middleware for extracting tenant ID from headers"""
    
    async def dispatch(self, request: Request, call_next):
        # Extract tenant ID from X-Tenant-Id header
        tenant_id = request.headers.get("X-Tenant-Id")
        
        # Set tenant ID in request state
        request.state.tenant_id = tenant_id
        response = await call_next(request)
        return response

class TracingMiddleware(BaseHTTPMiddleware):
    """Middleware for adding trace IDs to requests"""
    
    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("X-Trace-ID") or str(uuid.uuid4())
        span_id = str(uuid.uuid4())
        
        request.state.trace_id = trace_id
        request.state.span_id = span_id
        
        response = await call_next(request)
        
        response.headers["X-Trace-ID"] = trace_id
        response.headers["X-Span-ID"] = span_id
        
        return response

class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Middleware for handling idempotency keys"""
    
    async def dispatch(self, request: Request, call_next):
        idempotency_key = request.headers.get("Idempotency-Key")
        
        if idempotency_key and request.method in ["POST", "PUT", "PATCH"]:
            # For now, just pass through - full implementation would check cache
            pass
        
        response = await call_next(request)
        return response
