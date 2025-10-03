
import os
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends, HTTPException, status
from app.core.db import get_async_session
from app.core.di import get_llm_client, get_emb_client
from app.core.security import UserCtx

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

# Authentication dependencies (stubs for now)
def get_current_user() -> UserCtx:
    """Get current user from request (stub implementation)"""
    # This is a stub - in real implementation would extract from JWT token
    return UserCtx(id="test-user-id", role="reader", tenant_ids=["test-tenant"])

def require_admin(user: UserCtx = Depends(get_current_user)) -> UserCtx:
    """Require admin role"""
    if user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return user

# Rate limiting (stub)
def rate_limit():
    """Rate limiting dependency (stub)"""
    pass

def get_client_ip():
    """Get client IP (stub)"""
    return "127.0.0.1"
