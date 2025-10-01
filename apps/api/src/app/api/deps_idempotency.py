from __future__ import annotations
from typing import Optional
import time
from fastapi import Header, HTTPException, status, Request

from app.core.redis import get_redis
from app.core.config import settings

DEFAULT_TTL = int(getattr(settings, "IDEMP_TTL_HOURS", 24)) * 3600
MASTER_ENABLED = bool(getattr(settings, "IDEMPOTENCY_ENABLED", True))

async def idempotency_guard(
    request: Request,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key"),
    scope: str = "generic",
    ttl: int = DEFAULT_TTL,
):
    if not MASTER_ENABLED:
        return
    if not idempotency_key:
        return

    r = get_redis()
    key = f"idemp:{scope}:{idempotency_key}"

    try:
        set_ok = await r.set(key, int(time.time()), ex=ttl, nx=True)  # async client
    except AttributeError:
        set_ok = r.set(key, int(time.time()), ex=ttl, nx=True)  # sync stub

    if not set_ok:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="duplicate_request",
            headers={"Retry-After": str(ttl)},
        )
