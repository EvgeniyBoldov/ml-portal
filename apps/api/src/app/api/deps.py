
import os
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends, HTTPException, status, Request
from app.core.db import get_db
from app.core.di import get_llm_client, get_emb_client
from app.core.security import UserCtx
from app.core.redis import get_redis

# Re-export for routers/services
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async for s in get_db():
        yield s

async def db_uow() -> AsyncGenerator[AsyncSession, None]:
    """Unit of Work dependency that handles transactions automatically"""
    async for session in get_db():
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

def is_auth_enabled() -> bool:
    return (os.getenv("AUTH_ENABLED") or "false").lower() in {"1", "true", "yes", "on"}

# Client dependencies
def get_llm_client_mock():
    """Mock LLM client for testing"""
    return get_llm_client()

def get_redis_client():
    """Get Redis client for pub/sub and caching"""
    return get_redis()

# Authentication dependencies

def get_current_user_optional(request: Request) -> UserCtx | None:
    """Optional auth for dev/debugging - returns None if no auth provided
    
    Use ONLY for non-critical endpoints like SSE in dev mode.
    """
    from app.core.security import decode_jwt
    from app.core.config import get_settings
    
    settings = get_settings()

    # Always relax auth for SSE stream endpoint specifically
    # This avoids 401 on EventSource connections when cookies are missing in some envs
    path = request.url.path or ""
    if path.endswith("/api/v1/rag/events") or path.endswith("/rag/events"):
        # Try header/cookie first, otherwise allow anonymous mock in any ENV
        pass
    else:
        # For all non-SSE endpoints, enforce auth in production as before
        if settings.ENV == "production":
            return get_current_user(request)
    
    token = None
    
    # Try to get token from Authorization header first
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    
    # If no header token, try to get from httpOnly cookie
    if not token:
        token = request.cookies.get("access_token")
    
    if not token:
        # Fix #8: In production, return None instead of fake admin
        # For dev/local only, return limited mock user (reader, not admin)
        if settings.ENV == "production":
            return None
        return UserCtx(
            id="dev-user",
            email="dev@localhost",
            role="reader",  # Changed from admin to reader for safety
            tenant_ids=["fb983a10-c5f8-4840-a9d3-856eea0dc729"],  # Use default dev tenant
            scopes=["read"]  # Limited scopes
        )
    
    try:
        payload = decode_jwt(token)
        if payload.get("type") != "access":
            return None
        
        return UserCtx(
            id=payload["sub"],
            email=payload.get("email"),
            role=payload.get("role", "reader"),
            tenant_ids=payload.get("tenant_ids", []),
            scopes=payload.get("scopes", [])
        )
    except Exception:
        return None

# Authentication dependencies
def get_current_user(request: Request) -> UserCtx:
    """Get current user from JWT token in Authorization header or httpOnly cookie
    
    For SSE: EventSource automatically sends cookies with withCredentials: true.
    NO tokens in URL query params for security.
    """
    from app.core.security import decode_jwt
    
    token = None
    
    # Try to get token from Authorization header first
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    
    # If no header token, try to get from httpOnly cookie
    if not token:
        token = request.cookies.get("access_token")
    
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    payload = decode_jwt(token)
    
    # Validate token type
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    return UserCtx(
        id=payload["sub"],
        email=payload.get("email"),
        role=payload.get("role", "reader"),
        tenant_ids=payload.get("tenant_ids", []),
        scopes=payload.get("scopes", [])
    )

def require_admin(user: UserCtx = Depends(get_current_user)) -> UserCtx:
    """Require admin role"""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return user

def get_tenant_id(request: Request) -> str | None:
    """Get tenant_id from request state (set by middleware)"""
    return getattr(request.state, "tenant_id", None)

def require_tenant(request: Request) -> str:
    """Require tenant_id to be present"""
    tenant_id = get_tenant_id(request)
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant ID required"
        )
    return tenant_id

# Rate limiting (stub)
def rate_limit():
    """Rate limiting dependency (stub)"""
    pass

def get_client_ip():
    """Get client IP (stub)"""
    return "127.0.0.1"
