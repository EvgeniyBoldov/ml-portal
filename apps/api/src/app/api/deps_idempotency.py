from __future__ import annotations
from typing import Optional
import time
from uuid import UUID
from fastapi import Header, HTTPException, status, Request
from app.core.redis import get_redis
from app.core.config import get_settings

SENSITIVE_PATHS = {"/api/v1/auth/login", "/api/v1/auth/refresh"}

def _ttl_seconds() -> int:
    s = get_settings()
    return int(s.IDEMP_TTL_HOURS) * 3600

def _is_stream_request(request: Request) -> bool:
    accept = request.headers.get("accept", "")
    return "text/event-stream" in accept or request.url.path.endswith("/stream")

def _uuid_v4(s: str) -> bool:
    try:
        return UUID(s).version == 4
    except Exception:
        return False

async def idempotency_guard(
    request: Request,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    scope: str = "generic",
    ttl: int | None = None,
):
    s = get_settings()
    if not s.IDEMPOTENCY_ENABLED:
        return
    if not idempotency_key:
        return
    if not _uuid_v4(idempotency_key):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invalid_idempotency_key_format")

    if _is_stream_request(request) or request.url.path in SENSITIVE_PATHS:
        # validate presence/format only; do not cache
        return

    r = get_redis()
    key = f"{s.ENV}:idemp:{scope}:{idempotency_key}"
    ttl_sec = ttl if ttl is not None else _ttl_seconds()
    try:
        set_ok = await r.set(key, int(time.time()), ex=ttl_sec, nx=True)
    except AttributeError:
        set_ok = r.set(key, int(time.time()), ex=ttl_sec, nx=True)
    if not set_ok:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="IDEMPOTENCY_REPLAYED",
            headers={"Retry-After": str(ttl_sec)},
        )
