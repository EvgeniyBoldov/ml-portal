
from __future__ import annotations
from typing import Optional, Dict, Any, List, Union
from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
import hashlib
import time
import uuid

from app.core.db import get_session
from app.core.redis import get_redis
from app.core.security import get_bearer_token, decode_jwt, get_bearer_token_from_request, UserCtx
from app.core.config import settings
from app.repositories.users_repo import UsersRepository
from app.schemas.users import UserRole

# unified connectors
from app.core.di import get_llm_client as _get_llm_client, get_emb_client as _get_emb_client
from app.core.http.clients import LLMClientProtocol, EmbClientProtocol

def db_session():
    \"\"\"Real DB session dependency.\"\"\"
    yield from get_session()

# expose deps compatible with Depends(...)
def get_llm_client() -> LLMClientProtocol:
    return _get_llm_client()

def get_emb_client() -> EmbClientProtocol:
    return _get_emb_client()

def get_client_ip(request: Request) -> str:
    # trusted headers first, then client host
    for h in ("x-forwarded-for", "x-real-ip"):
        if h in request.headers:
            return request.headers[h].split(",")[0].strip()
    client = request.client
    return getattr(client, "host", "unknown")

async def rate_limit(request: Request, key: str, limit: int, window_sec: int = 60, login: str = None) -> None:
    \"\"\"Simple fixed-window rate limit on IP+key+login using Redis.
    Raises 429 if the number of hits in the current window exceeds `limit`.
    \"\"\"
    try:
        r = get_redis()
        ip = get_client_ip(request)
        now = int(time.time())
        window = now - (now % window_sec)
        
        # Include login in rate limit key if provided
        rl_key = f\"rl:{key}:{ip}:{login or '-'}:{window}\"
        
        try:
            result = await r.set(rl_key, \"1\", nx=True, ex=window_sec)
            if result:
                if hasattr(request, 'state'):
                    request.state.rate_limit_headers = {
                        \"X-RateLimit-Limit\": str(limit),
                        \"X-RateLimit-Remaining\": str(limit - 1),
                        \"X-RateLimit-Window\": str(window_sec),
                        \"X-RateLimit-Reset\": str(window + window_sec)
                    }
                return
            cur = await r.incr(rl_key)
            remaining = max(0, limit - cur)
            if hasattr(request, 'state'):
                request.state.rate_limit_headers = {
                    \"X-RateLimit-Limit\": str(limit),
                    \"X-RateLimit-Remaining\": str(remaining),
                    \"X-RateLimit-Window\": str(window_sec),
                    \"X-RateLimit-Reset\": str(window + window_sec)
                }
            if cur > limit:
                retry_after = window_sec - (now % window_sec) or window_sec
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=\"rate_limited\",
                    headers={
                        \"Retry-After\": str(retry_after),
                        \"X-RateLimit-Limit\": str(limit),
                        \"X-RateLimit-Remaining\": \"0\",
                        \"X-RateLimit-Window\": str(window_sec),
                        \"X-RateLimit-Reset\": str(window + window_sec)
                    }
                )
        except AttributeError:
            # sync client fallback
            result = r.set(rl_key, \"1\", nx=True, ex=window_sec)
            if result:
                return
            cur = r.incr(rl_key)
            remaining = max(0, limit - cur)
            if hasattr(request, 'state'):
                request.state.rate_limit_headers = {
                    \"X-RateLimit-Limit\": str(limit),
                    \"X-RateLimit-Remaining\": str(remaining),
                    \"X-RateLimit-Window\": str(window_sec),
                    \"X-RateLimit-Reset\": str(window + window_sec)
                }
            if cur > limit:
                retry_after = window_sec - (now % window_sec) or window_sec
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=\"rate_limited\",
                    headers={
                        \"Retry-After\": str(retry_after),
                        \"X-RateLimit-Limit\": str(limit),
                        \"X-RateLimit-Remaining\": \"0\",
                        \"X-RateLimit-Window\": str(window_sec),
                        \"X-RateLimit-Reset\": str(window + window_sec)
                    }
                )
    except Exception as e:
        # fail-open
        print(f\"Rate limiting skipped due to error: {e}\")
        return

def _ensure_access(payload: Dict[str, Any]) -> None:
    if payload.get(\"typ\") != \"access\":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=\"invalid_token_type\")

def get_current_user(token: str = Depends(get_bearer_token), session: Session = Depends(db_session)) -> UserCtx:
    \"\"\"Resolve user from Bearer access JWT and DB.\"\"\"
    payload = decode_jwt(token)
    _ensure_access(payload)
    sub = payload.get(\"sub\")
    if not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=\"invalid_token\")
    
    tenant_id = None
    tenant_id_str = payload.get(\"tenant_id\")
    if tenant_id_str:
        try:
            tenant_id = uuid.UUID(tenant_id_str)
        except ValueError:
            pass
    
    repo = UsersRepository(session)
    user = repo.get(sub)
    if not user or getattr(user, \"is_active\", True) is False:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=\"user_not_found_or_inactive\")
    
    return UserCtx(id=str(user.id), role=user.role, tenant_id=tenant_id)

from app.schemas.users import UserRole
def require_roles(*roles: Union[str, UserRole]) -> callable:
    role_values = [r.value if isinstance(r, UserRole) else r for r in roles]
    def check_roles(current_user: UserCtx = Depends(get_current_user)) -> UserCtx:
        user_role = current_user.role
        if user_role not in role_values:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f\"Access denied. Required roles: {role_values}, user role: {user_role}\"
            )
        return current_user
    return check_roles

def require_admin(current_user: UserCtx = Depends(require_roles(UserRole.ADMIN))) -> UserCtx:
    return current_user

def require_user(current_user: UserCtx = Depends(get_current_user)) -> UserCtx:
    return current_user

def require_editor_or_admin(current_user: UserCtx = Depends(require_roles(UserRole.EDITOR, UserRole.ADMIN))) -> UserCtx:
    return current_user

def require_reader_or_above(current_user: UserCtx = Depends(require_roles(UserRole.READER, UserRole.EDITOR, UserRole.ADMIN))) -> UserCtx:
    return current_user

def get_current_user_optional(request: Request) -> Optional[UserCtx]:
    try:
        token = get_bearer_token_from_request(request)
        payload = decode_jwt(token)
        _ensure_access(payload)
        sub = payload.get(\"sub\")
        if not sub:
            return None
        tenant_id = None
        tenant_id_str = payload.get(\"tenant_id\")
        if tenant_id_str:
            try:
                tenant_id = uuid.UUID(tenant_id_str)
            except ValueError:
                pass
        repo = UsersRepository(next(get_session()))
        user = repo.get(sub)
        if not user or getattr(user, \"is_active\", True) is False:
            return None
        return UserCtx(id=str(user.id), role=user.role, tenant_id=tenant_id)
    except Exception:
        return None
