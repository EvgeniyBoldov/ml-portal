
import os
import uuid as _uuid
import time
from dataclasses import dataclass
from typing import AsyncGenerator, Callable

from fastapi import Depends, HTTPException, status, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.di import get_llm_client
from app.core.redis import get_redis
from app.core.security import UserCtx
from app.models.chat import Chats

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
            role="reader",
            tenant_ids=[],
            scopes=["read"]
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


async def get_current_user_sse(request: Request) -> UserCtx:
    """Auth dependency for SSE endpoints.
    
    Accepts token from:
    1. Authorization header (Bearer token)
    2. httpOnly cookie (access_token)
    
    EventSource automatically sends cookies with credentials: 'include'.
    DO NOT use query params for tokens - they leak in logs and browser history.
    """
    from app.core.security import decode_jwt
    from app.core.config import get_settings

    token = None
    settings = get_settings()

    # 1) Authorization header
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]

    # 2) httpOnly cookie (preferred for SSE)
    if not token:
        token = request.cookies.get("access_token")

    # 3) query param fallback for dev/local SSE clients
    # In production keep strict header/cookie-only auth.
    if not token and settings.ENV != "production":
        token = request.query_params.get("token")

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization. Use httpOnly cookie or Authorization header.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    payload = decode_jwt(token)

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

# ── Chat context resolution ───────────────────────────────────────────────────────────


@dataclass
class ChatContext:
    """Resolved chat context: validated chat record + tenant access."""
    chat_id: str
    tenant_id: str  # str(UUID) — ready for service layer
    user_id: str


async def resolve_chat_context(
    chat_id: str,
    session: AsyncSession = Depends(db_session),
    current_user: UserCtx = Depends(get_current_user),
) -> ChatContext:
    """Load chat, verify tenant assignment and user access.

    Raises HTTPException on:
    - Invalid chat_id UUID
    - Chat not found
    - Chat has no tenant
    - User not in chat's tenant
    """
    try:
        chat_uuid = _uuid.UUID(chat_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid chat ID")

    result = await session.execute(select(Chats).where(Chats.id == chat_uuid))
    chat_row = result.scalar_one_or_none()
    if not chat_row:
        raise HTTPException(status_code=404, detail="Chat not found")
    if not chat_row.tenant_id:
        raise HTTPException(status_code=400, detail="Chat has no tenant assigned")

    tenant_id = _uuid.UUID(str(chat_row.tenant_id))
    user_tenant_ids = {_uuid.UUID(str(tid)) for tid in (current_user.tenant_ids or [])}
    if user_tenant_ids and tenant_id not in user_tenant_ids:
        raise HTTPException(status_code=403, detail="Access denied: user does not belong to chat tenant")

    return ChatContext(
        chat_id=str(chat_uuid),
        tenant_id=str(tenant_id),
        user_id=str(current_user.id),
    )


def get_client_ip(request: Request) -> str:
    """Best-effort client IP for audit/rate-limit keys."""
    if request.client and request.client.host:
        return str(request.client.host)
    return "unknown"


def rate_limit_dependency(
    *,
    key_prefix: str,
    rpm: int,
    rph: int,
) -> Callable[[Request], None]:
    """
    Build Redis-backed rate-limit dependency (fail-open).

    Uses fixed windows:
    - minute key TTL: 60s
    - hour key TTL: 3600s
    """

    async def _check(request: Request) -> None:
        user_id = None
        user = getattr(request.state, "user", None)
        if user is not None:
            user_id = getattr(user, "id", None)

        key = f"user:{user_id}" if user_id else f"ip:{get_client_ip(request)}"
        now = int(time.time())
        redis = get_redis()
        minute_key = f"ratelimit:{key_prefix}:{key}:minute:{now // 60}"
        hour_key = f"ratelimit:{key_prefix}:{key}:hour:{now // 3600}"

        try:
            minute_count = await redis.incr(minute_key)
            if minute_count == 1:
                await redis.expire(minute_key, 60)
            if minute_count > rpm:
                retry_after = 60 - (now % 60)
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Retry after {retry_after} seconds.",
                    headers={"Retry-After": str(retry_after)},
                )

            hour_count = await redis.incr(hour_key)
            if hour_count == 1:
                await redis.expire(hour_key, 3600)
            if hour_count > rph:
                retry_after = 3600 - (now % 3600)
                raise HTTPException(
                    status_code=429,
                    detail=f"Rate limit exceeded. Retry after {retry_after} seconds.",
                    headers={"Retry-After": str(retry_after)},
                )
        except HTTPException:
            raise
        except Exception:
            # Fail-open to avoid auth/chat hard outage on Redis issues.
            return

    return _check
