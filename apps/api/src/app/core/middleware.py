from __future__ import annotations
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.security import decode_jwt
import logging

logger = logging.getLogger(__name__)

class TenantMiddleware(BaseHTTPMiddleware):
    """Middleware to extract tenant_id from request headers or JWT token"""
    
    def __init__(self, app, exclude_paths: list[str] | None = None):
        super().__init__(app)
        self.exclude_paths = exclude_paths or [
            "/docs",
            "/redoc", 
            "/openapi.json",
            "/auth/login",
            "/auth/refresh",
            "/auth/.well-known/jwks.json",
            "/health",
            "/metrics"
        ]
    
    async def dispatch(self, request: Request, call_next):
        # Skip tenant extraction for excluded paths
        if request.url.path in self.exclude_paths:
            return await call_next(request)
        
        tenant_id = None
        
        # Try to get tenant_id from X-Tenant-Id header first
        tenant_header = request.headers.get("X-Tenant-Id")
        if tenant_header:
            tenant_id = tenant_header.strip()
        
        # If no header, try to extract from JWT token
        if not tenant_id:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                try:
                    token = auth_header.split(" ")[1]
                    payload = decode_jwt(token)
                    tenant_ids = payload.get("tenant_ids", [])
                    if tenant_ids:
                        tenant_id = tenant_ids[0]  # Use first tenant
                except Exception as e:
                    logger.warning(f"Failed to extract tenant from JWT: {e}")
        
        # Validate tenant_id format (should be UUID)
        if tenant_id:
            try:
                import uuid
                uuid.UUID(tenant_id)  # Validate UUID format
            except ValueError:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"detail": "Invalid tenant ID format"}
                )
        
        # Store tenant_id in request state
        request.state.tenant_id = tenant_id
        
        # For protected endpoints, require tenant_id
        if not tenant_id and self._is_protected_endpoint(request.url.path):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"detail": "Tenant ID required"}
            )
        
        response = await call_next(request)
        return response
    
    def _is_protected_endpoint(self, path: str) -> bool:
        """Check if endpoint requires tenant_id"""
        protected_prefixes = [
            "/api/v1/chats",
            "/api/v1/users",
            "/api/v1/rag",
            "/api/v1/artifacts"
        ]
        return any(path.startswith(prefix) for prefix in protected_prefixes)
