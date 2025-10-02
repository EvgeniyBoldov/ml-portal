"""
app/api/deps.py
- Fixes verify_token import path.
- Provides stubs for rate_limit, get_client_ip, and embedding/LLM clients.
Replace stubs with real implementations as you wire them.
"""
from __future__ import annotations
from typing import AsyncIterator, Any, Optional

from contextlib import asynccontextmanager
from fastapi import Header, Request

# ✅ Correct import for JWT utils
try:
    from app.core.security_jwt import verify_token  # type: ignore
except Exception:
    from app.core.security import verify_token  # type: ignore  # fallback

# --- DB session deps (async preferred) ---
try:
    from app.core.db import get_async_session as _get_async_session  # type: ignore
except Exception:
    _get_async_session = None  # type: ignore

try:
    from app.core.db import get_session as _get_session  # type: ignore
except Exception:
    _get_session = None  # type: ignore

@asynccontextmanager
async def db_session() -> AsyncIterator[Any]:
    if _get_async_session is not None:
        async with _get_async_session() as s:  # type: ignore
            yield s; return
    if _get_session is not None:
        with _get_session() as s:  # type: ignore
            yield s; return
    raise RuntimeError("Implement app.core.db.get_async_session or get_session")

# --- Simple rate limit stub ---
class RateLimitResult:
    def __init__(self, allowed: bool, remaining: int = 1, reset_s: int = 1):
        self.allowed, self.remaining, self.reset_s = allowed, remaining, reset_s

async def rate_limit(request: Request, limit: str = "10/m") -> RateLimitResult:
    return RateLimitResult(True, remaining=9999, reset_s=1)

# --- Client IP ---
def get_client_ip(request: Request) -> str:
    xfwd = request.headers.get("x-forwarded-for")
    return xfwd.split(",")[0].strip() if xfwd else (request.client.host if request.client else "0.0.0.0")

# --- Embeddings / LLM client stubs ---
def _opt(path: str):
    try:
        m, a = path.rsplit(":", 1); mod = __import__(m, fromlist=[a]); return getattr(mod, a)
    except Exception:
        return None

def get_emb_client():
    f = _opt("app.services.embeddings:EmbeddingsClient"); return f() if f else object()

def get_llm_client():
    f = _opt("app.services.llm:LLMClient"); return f() if f else object()

def get_bearer_token(authorization: Optional[str] = Header(None)) -> Optional[str]:
    if not authorization: return None
    scheme, _, token = authorization.partition(" ")
    return token if scheme.lower() == "bearer" and token else None

# --- Auth dependencies ---
from pydantic import BaseModel

class UserCtx(BaseModel):
    """User context for testing"""
    id: str = "test-user"
    role: str = "user"
    scopes: list = []

    class Config:
        arbitrary_types_allowed = True

def get_current_user(token: Optional[str] = None) -> UserCtx:
    """Get current user from token (stub for testing)"""
    return UserCtx(id="test-user", role="user")

def require_admin(user: UserCtx = None) -> UserCtx:
    """Require admin role (stub for testing)"""
    if user is None:
        user = UserCtx(id="admin-user", role="admin")
    if user.role != "admin":
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Admin access required")
    return user
