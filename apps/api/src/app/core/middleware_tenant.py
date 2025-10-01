"""
app/core/middleware_tenant.py
Enforces X-Tenant-Id on protected paths, excluding public/auth endpoints.
"""
from __future__ import annotations
import re
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

UUID_V4_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.I)

EXCLUDE_PATHS = (
    "/health", "/metrics", "/openapi.json", "/docs", "/redoc", "/.well-known/jwks.json",
    "/api/v1/auth/login", "/api/v1/auth/refresh", "/api/v1/auth/logout",
)

class TenantMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, header_name: str = "x-tenant-id"):
        super().__init__(app); self.header_name = header_name

    async def dispatch(self, request, call_next):
        path = request.url.path
        if any(path.startswith(p) for p in EXCLUDE_PATHS):
            return await call_next(request)
        tenant_id = request.headers.get("X-Tenant-Id")
        if not tenant_id or not UUID_V4_RE.match(tenant_id):
            return JSONResponse(
                {"type":"about:blank","title":"Tenant header required","status":400,"detail":"Provide X-Tenant-Id UUIDv4"},
                status_code=400, headers={"Content-Type":"application/problem+json"}
            )
        request.state.tenant_id = tenant_id
        return await call_next(request)
