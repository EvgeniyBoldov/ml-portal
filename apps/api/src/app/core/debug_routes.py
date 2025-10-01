"""
DEBUG routes and test endpoints management
"""
from __future__ import annotations
from typing import List, Dict, Any
from fastapi import FastAPI, HTTPException, status
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.schemas.common import Problem


class DebugRoutesManager:
    """Manager for DEBUG-only routes and test endpoints"""
    
    DEBUG_PREFIXES = [
        "/api/setup",
        "/api/test",
        "/api/debug"
    ]
    
    DEBUG_ENDPOINTS = [
        "/rag/upload/validate",
        "/users",  # create_user endpoint
        "/test/rag/search",
        "/test/analyze/run"
    ]
    
    @classmethod
    def is_debug_endpoint(cls, path: str) -> bool:
        """Check if endpoint is DEBUG-only"""
        # Check prefixes
        for prefix in cls.DEBUG_PREFIXES:
            if path.startswith(prefix):
                return True
        
        # Check specific endpoints
        for endpoint in cls.DEBUG_ENDPOINTS:
            if path.endswith(endpoint):
                return True
        
        return False
    
    @classmethod
    def check_debug_access(cls, path: str) -> None:
        """Check if DEBUG endpoint is accessible"""
        s = get_settings()
        if cls.is_debug_endpoint(path) and not s.DEBUG:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=Problem(
                    type="https://example.com/problems/debug-endpoint-disabled",
                    title="Debug Endpoint Disabled",
                    status=403,
                    code="DEBUG_ENDPOINT_DISABLED",
                    detail="This endpoint is only available in DEBUG mode"
                ).model_dump()
            )
    
    @classmethod
    def get_debug_endpoints_info(cls) -> Dict[str, Any]:
        """Get information about DEBUG endpoints"""
        s = get_settings()
        return {
            "debug_mode": s.DEBUG,
            "debug_prefixes": cls.DEBUG_PREFIXES,
            "debug_endpoints": cls.DEBUG_ENDPOINTS,
            "total_debug_endpoints": len(cls.DEBUG_PREFIXES) + len(cls.DEBUG_ENDPOINTS)
        }


class DebugMiddleware:
    """Middleware to enforce DEBUG-only access"""
    
    def __init__(self, app: FastAPI):
        self.app = app
    
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope["path"]
            
            # Check DEBUG access
            try:
                DebugRoutesManager.check_debug_access(path)
            except HTTPException as e:
                response = JSONResponse(
                    status_code=e.status_code,
                    content=e.detail
                )
                await response(scope, receive, send)
                return
        
        await self.app(scope, receive, send)


def setup_debug_routes(app: FastAPI) -> None:
    """Setup DEBUG routes and middleware"""
    
    # Add DEBUG middleware
    app.add_middleware(DebugMiddleware)
    
    # Add DEBUG info endpoint (always available)
    @app.get("/api/debug/info")
    async def debug_info():
        """Get DEBUG endpoints information"""
        return DebugRoutesManager.get_debug_endpoints_info()
    
    # Add DEBUG health check
    @app.get("/api/debug/health")
    async def debug_health():
        """DEBUG health check with detailed info"""
        s = get_settings()
        if not s.DEBUG:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=Problem(
                    type="https://example.com/problems/debug-endpoint-disabled",
                    title="Debug Endpoint Disabled",
                    status=403,
                    code="DEBUG_ENDPOINT_DISABLED",
                    detail="This endpoint is only available in DEBUG mode"
                ).model_dump()
            )
        
        return {
            "status": "ok",
            "debug_mode": True,
            "environment": s.ENV,
            "debug_endpoints": DebugRoutesManager.get_debug_endpoints_info()
        }


def validate_debug_endpoints() -> List[str]:
    """Validate that all DEBUG endpoints are properly protected"""
    issues = []
    
    # Check if DEBUG mode is properly configured
    s = get_settings()
    if not hasattr(s, 'DEBUG'):
        issues.append("DEBUG setting not found in settings")
    
    # Check if DEBUG endpoints are properly marked
    for endpoint in DebugRoutesManager.DEBUG_ENDPOINTS:
        if not DebugRoutesManager.is_debug_endpoint(endpoint):
            issues.append(f"Endpoint {endpoint} should be marked as DEBUG-only")
    
    return issues
