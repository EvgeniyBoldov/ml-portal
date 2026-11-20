from __future__ import annotations
import json
from typing import Any, Dict, Optional
from app.core.logging import get_logger

logger = get_logger(__name__)


class IdempotencyManager:
    """Canonical Redis-based idempotency manager.

    Usage:
        idem = IdempotencyManager(redis, prefix="chat:message:")
        cached = await idem.get_cached_result(key)
        await idem.cache_result(key, data)
    """
    
    def __init__(
        self,
        redis_client,
        prefix: str = "chat:message:",
        ttl_seconds: int = 86400,
    ):
        self.redis = redis_client
        self.prefix = prefix
        self.ttl_seconds = ttl_seconds
    
    def _make_key(self, key: str) -> str:
        return f"{self.prefix}{key}"

    async def get_cached_result(self, key: str) -> Optional[Dict[str, Any]]:
        """Get cached result from Redis"""
        try:
            cache_key = self._make_key(key)
            cached_data = await self.redis.get(cache_key)
            if cached_data:
                return json.loads(cached_data)
        except Exception as e:
            logger.warning(f"Failed to get cached result: {e}")
        return None
    
    async def cache_result(self, key: str, data: Dict[str, Any]):
        """Cache result in Redis"""
        try:
            cache_key = self._make_key(key)
            await self.redis.setex(
                cache_key,
                self.ttl_seconds,
                json.dumps(data)
            )
            logger.debug(f"Cached result for key: {self.prefix}{key}")
        except Exception as e:
            logger.warning(f"Failed to cache result: {e}")

    async def delete(self, key: str) -> bool:
        """Delete cached result. Returns True if key existed."""
        try:
            cache_key = self._make_key(key)
            return bool(await self.redis.delete(cache_key))
        except Exception as e:
            logger.warning(f"Failed to delete cached result: {e}")
            return False
