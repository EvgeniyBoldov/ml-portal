"""
Redis cache and distributed locks implementation
"""
from __future__ import annotations
import json
from app.core.logging import get_logger
from typing import Any, Optional
import redis.asyncio as redis
from app.core.config import get_settings

logger = get_logger(__name__)

class RedisCache:
    """Redis cache with SCAN-based operations and index sets"""
    
    def __init__(self):
        self.redis_client: Optional[redis.Redis] = None
        self._connection_pool: Optional[redis.ConnectionPool] = None
    
    async def connect(self):
        """Connect to Redis"""
        settings = get_settings()
        self._connection_pool = redis.ConnectionPool.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=20
        )
        self.redis_client = redis.Redis(connection_pool=self._connection_pool)
        
        # Test connection
        await self.redis_client.ping()
        logger.info("Connected to Redis")
    
    async def disconnect(self):
        """Disconnect from Redis"""
        if self.redis_client:
            await self.redis_client.close()
        if self._connection_pool:
            await self._connection_pool.disconnect()
        logger.info("Disconnected from Redis")
    
    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if not self.redis_client:
            return None
        
        try:
            value = await self.redis_client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Redis get error for key {key}: {e}")
            return None
    
    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache with optional TTL"""
        if not self.redis_client:
            return False
        
        try:
            serialized = json.dumps(value, default=str)
            if ttl:
                await self.redis_client.setex(key, ttl, serialized)
            else:
                await self.redis_client.set(key, serialized)
            return True
        except Exception as e:
            logger.error(f"Redis set error for key {key}: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete key from cache"""
        if not self.redis_client:
            return False
        
        try:
            result = await self.redis_client.delete(key)
            return result > 0
        except Exception as e:
            logger.error(f"Redis delete error for key {key}: {e}")
            return False
    
    
    
    


# Global cache instance
_cache: Optional[RedisCache] = None

async def get_cache() -> RedisCache:
    """Get global cache instance"""
    global _cache
    if _cache is None:
        _cache = RedisCache()
        await _cache.connect()
    return _cache


# Cache decorators
def cache_key(prefix: str, *args, **kwargs) -> str:
    """Generate cache key from prefix and arguments"""
    key_parts = [prefix]
    
    # Add positional arguments
    for arg in args:
        if isinstance(arg, (str, int, float)):
            key_parts.append(str(arg))
        elif hasattr(arg, 'id'):
            key_parts.append(str(arg.id))
        else:
            key_parts.append(str(arg))
    
    # Add keyword arguments
    for k, v in sorted(kwargs.items()):
        if isinstance(v, (str, int, float)):
            key_parts.append(f"{k}:{v}")
        elif hasattr(v, 'id'):
            key_parts.append(f"{k}:{v.id}")
        else:
            key_parts.append(f"{k}:{v}")
    
    return ":".join(key_parts)


def cached(ttl: int = 300, key_prefix: str = "cache"):
    """Decorator for caching function results"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Generate cache key
            key = cache_key(key_prefix, func.__name__, *args, **kwargs)
            
            # Try to get from cache
            cache = await get_cache()
            cached_result = await cache.get(key)
            if cached_result is not None:
                return cached_result
            
            # Execute function
            result = await func(*args, **kwargs)
            
            # Cache result
            await cache.set(key, result, ttl)
            
            return result
        return wrapper
    return decorator

