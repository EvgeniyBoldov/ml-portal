from __future__ import annotations
import redis
from .config import get_settings

_client = None

def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        url = get_settings().REDIS_URL
        _client = redis.from_url(url, decode_responses=True)
    return _client
