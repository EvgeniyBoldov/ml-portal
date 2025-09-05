from __future__ import annotations
from typing import Optional
from redis.asyncio import Redis
from .config import settings

_redis: Optional[Redis] = None

def get_redis() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis
