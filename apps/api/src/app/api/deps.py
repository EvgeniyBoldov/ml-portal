
import os
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends, HTTPException, status, Request
from core.db import get_async_session
from core.di import get_llm_client, get_emb_client
from core.security import UserCtx

# Re-export for routers/services
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async for s in get_async_session():
        yield s

def is_auth_enabled() -> bool:
    return (os.getenv("AUTH_ENABLED") or "false").lower() in {"1", "true", "yes", "on"}

# Client dependencies
def get_llm_client_mock():
    """Mock LLM client for testing"""
    return get_llm_client()

# Authentication dependencies
def get_current_user(request: Request) -> UserCtx:
    """Get current user from JWT token in Authorization header or cookies"""
    from core.security import decode_jwt
    
    token = None
    
    # Try to get token from Authorization header first
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    
    # If no header token, try to get from cookies
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
