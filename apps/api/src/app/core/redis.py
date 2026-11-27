from __future__ import annotations
import redis.asyncio as redis
from .config import get_settings

_client = None

def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        url = get_settings().REDIS_URL
        _client = redis.from_url(url, decode_responses=True)
    return _client


async def dispose_redis() -> None:
    """Close and forget the loop-bound client after an isolated Celery task."""
    global _client
    client, _client = _client, None
    if client is not None:
        await client.aclose()
