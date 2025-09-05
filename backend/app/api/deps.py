from __future__ import annotations
from typing import Optional, Dict, Any
from fastapi import Depends, HTTPException, status, Request
from sqlalchemy.orm import Session
import hashlib
import time

from app.core.db import get_session
from app.core.redis import get_redis
from app.core.security import get_bearer_token, decode_jwt
from app.repositories.users_repo import UsersRepo

def db_session():
    """Real DB session dependency."""
    yield from get_session()

async def rate_limit(request: Request, key: str, limit: int, window_sec: int = 60) -> None:
    """Simple fixed-window rate limit on IP+key using Redis.
    Raises 429 if the number of hits in the current window exceeds `limit`.
    """
    r = get_redis()
    ip = request.client.host if request.client else "unknown"
    now = int(time.time())
    window = now - (now % window_sec)
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
