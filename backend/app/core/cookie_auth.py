"""
Cookie-based authentication with CSRF protection
"""
from __future__ import annotations
import secrets
from typing import Optional
from fastapi import Request, Response, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware

from .config import settings
from .security import decode_jwt

# CSRF token storage (in production, use Redis)
_csrf_tokens = {}

class CSRFMiddleware(BaseHTTPMiddleware):
    """CSRF protection middleware"""
    
    def __init__(self, app, secret_key: str = None):
        super().__init__(app)
        self.secret_key = secret_key or settings.JWT_SECRET
    
    async def dispatch(self, request: Request, call_next):
        # Skip CSRF for safe methods and auth endpoints
        if request.method in ["GET", "HEAD", "OPTIONS"]:
            return await call_next(request)
        
        # Skip CSRF for auth endpoints
        if request.url.path.startswith("/api/auth/"):
            return await call_next(request)
        
        # Check CSRF token
        csrf_token = request.headers.get("X-CSRF-Token")
        if not csrf_token:
            return HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": {"code": "csrf_missing", "message": "CSRF token required"}}
            )
        
        # Validate CSRF token
        if not self._validate_csrf_token(csrf_token, request):
            return HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error": {"code": "csrf_invalid", "message": "Invalid CSRF token"}}
            )
        
        return await call_next(request)
    
    def _validate_csrf_token(self, token: str, request: Request) -> bool:
        """Validate CSRF token"""
        # In production, implement proper CSRF token validation
        # For now, just check if token exists in our storage
        return token in _csrf_tokens

def generate_csrf_token() -> str:
    """Generate CSRF token"""
    token = secrets.token_urlsafe(32)
    _csrf_tokens[token] = True
    return token

def set_auth_cookies(response: Response, access_token: str, refresh_token: str, csrf_token: str):
    """Set authentication cookies"""
    # Access token cookie (short-lived)
    response.set_cookie(
        key="access_token",
        value=access_token,
        max_age=settings.ACCESS_TTL_SECONDS,
        httponly=True,
        secure=not settings.DEBUG,  # HTTPS only in production
        samesite="lax"
    )
    
    # Refresh token cookie (long-lived)
    response.set_cookie(
        key="refresh_token", 
        value=refresh_token,
        max_age=settings.REFRESH_TTL_DAYS * 86400,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="lax"
    )
    
    # CSRF token cookie (not httpOnly for JS access)
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        max_age=settings.REFRESH_TTL_DAYS * 86400,
        httponly=False,  # Allow JS access
        secure=not settings.DEBUG,
        samesite="lax"
    )

def clear_auth_cookies(response: Response):
    """Clear authentication cookies"""
    response.delete_cookie("access_token")
    response.delete_cookie("refresh_token") 
    response.delete_cookie("csrf_token")

def get_token_from_cookie(request: Request) -> Optional[str]:
    """Get access token from cookie"""
    return request.cookies.get("access_token")

def get_refresh_token_from_cookie(request: Request) -> Optional[str]:
    """Get refresh token from cookie"""
    return request.cookies.get("refresh_token")

def get_csrf_token_from_cookie(request: Request) -> Optional[str]:
    """Get CSRF token from cookie"""
    return request.cookies.get("csrf_token")

class CookieAuthBearer(HTTPBearer):
    """Cookie-based authentication with Bearer fallback"""
    
    def __init__(self, auto_error: bool = True):
        super().__init__(auto_error=auto_error)
    
    async def __call__(self, request: Request) -> Optional[HTTPAuthorizationCredentials]:
        # Try cookie first
        token = get_token_from_cookie(request)
        if token:
            return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)
        
        # Fallback to header
        return await super().__call__(request)

# Cookie auth dependency
cookie_auth = CookieAuthBearer(auto_error=False)

def get_cookie_token(credentials: Optional[HTTPAuthorizationCredentials] = None) -> Optional[str]:
    """Get token from cookie or header"""
    if credentials and credentials.scheme.lower() == "bearer":
        return credentials.credentials
    return None
