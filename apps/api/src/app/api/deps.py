from __future__ import annotations
from typing import Optional, Dict, Any, List, Union
from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
import hashlib
import time
import uuid

from app.core.db import get_session
from app.core.redis import get_redis
from app.core.security import get_bearer_token, decode_jwt
from app.core.config import settings
from app.repositories.users_repo import UsersRepo
from app.schemas.admin import UserRole

def db_session():
    """Real DB session dependency."""
    yield from get_session()

async def rate_limit(request: Request, key: str, limit: int, window_sec: int = 60, login: str = None) -> None:
    """Simple fixed-window rate limit on IP+key+login using Redis.
    Raises 429 if the number of hits in the current window exceeds `limit`.
    """
    r = get_redis()
    ip = get_client_ip(request)
    now = int(time.time())
    window = now - (now % window_sec)
    
    # Include login in rate limit key if provided
    if login:
        rl_key = f"rl:{key}:{ip}:{login}:{window}"
    else:
        rl_key = f"rl:{key}:{ip}:{window}"
    # Use Lua for atomic INCR+EXPIRE if available; fallback to simple ops
    try:
        cur = await r.incr(rl_key)  # type: ignore[attr-defined]
        if cur == 1:
            await r.expire(rl_key, window_sec)  # type: ignore[attr-defined]
        if cur > limit:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate_limited")
    except AttributeError:
        # In case a sync client was wired accidentally
        cur = r.incr(rl_key)  # type: ignore
        if cur == 1:
            r.expire(rl_key, window_sec)  # type: ignore
        if cur > limit:
            raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail="rate_limited")

def _ensure_access(payload: Dict[str, Any]) -> None:
    if payload.get("typ") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token_type")

def get_current_user(token: str = Depends(get_bearer_token), session: Session = Depends(db_session)) -> Dict[str, Any]:
    """Resolve user from Bearer access JWT and DB."""
    payload = decode_jwt(token)
    _ensure_access(payload)
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid_token")
    repo = UsersRepo(session)
    user = repo.get(sub)
    if not user or getattr(user, "is_active", True) is False:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="user_not_found_or_inactive")
    return {"id": str(user.id), "login": user.login, "role": user.role, "fio": getattr(user, "fio", None)}


def require_roles(*roles: Union[str, UserRole]) -> callable:
    """RBAC dependency factory. Returns a dependency that requires specific roles."""
    role_values = [r.value if isinstance(r, UserRole) else r for r in roles]
    
    def check_roles(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
        user_role = current_user.get("role")
        if user_role not in role_values:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required roles: {role_values}, user role: {user_role}"
            )
        return current_user
    
    return check_roles


def require_admin(current_user: Dict[str, Any] = Depends(require_roles(UserRole.ADMIN))) -> Dict[str, Any]:
    """Require admin role."""
    return current_user

def require_upload_permission(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Require upload permission (editor, admin, or reader if enabled)."""
    user_role = current_user.get("role")
    
    # Admin and editor always have upload permission
    if user_role in ["admin", "editor"]:
        return current_user
    
    # Reader can upload if enabled
    if user_role == "reader" and settings.ALLOW_READER_UPLOADS:
        return current_user
    
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "error": {
                "code": "upload_forbidden",
                "message": "Upload permission denied. Reader uploads are disabled."
            }
        }
    )


def get_request_id(request: Request) -> str:
    """Extract or generate request ID."""
    request_id = request.headers.get("X-Request-ID")
    if not request_id:
        request_id = str(uuid.uuid4())
    return request_id


def get_client_ip(request: Request) -> str:
    """Extract client IP considering X-Forwarded-For header."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def get_user_agent(request: Request) -> Optional[str]:
    """Extract user agent."""
    return request.headers.get("User-Agent")
