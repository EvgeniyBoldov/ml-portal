"""
Redis cache and distributed locks implementation
"""
from __future__ import annotations
import asyncio
import json
from app.core.logging import get_logger
import time
import uuid
from typing import Any, Dict, List, Optional, Union
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
    
    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern using SCAN"""
        if not self.redis_client:
            return 0
        
        try:
            deleted_count = 0
            async for key in self.redis_client.scan_iter(match=pattern):
                result = await self.redis_client.delete(key)
                deleted_count += result
            return deleted_count
        except Exception as e:
            logger.error(f"Redis delete pattern error for {pattern}: {e}")
            return 0
    
    async def add_to_index(self, index_name: str, key: str) -> bool:
        """Add key to index set"""
        if not self.redis_client:
            return False
        
        try:
            await self.redis_client.sadd(index_name, key)
            return True
        except Exception as e:
            logger.error(f"Redis add to index error for {index_name}: {e}")
            return False
    
    async def remove_from_index(self, index_name: str, key: str) -> bool:
        """Remove key from index set"""
        if not self.redis_client:
            return False
        
        try:
            result = await self.redis_client.srem(index_name, key)
            return result > 0
        except Exception as e:
            logger.error(f"Redis remove from index error for {index_name}: {e}")
            return False
    
    async def get_index_keys(self, index_name: str) -> List[str]:
        """Get all keys in index set"""
        if not self.redis_client:
            return []
        
        try:
            keys = await self.redis_client.smembers(index_name)
            return list(keys)
        except Exception as e:
            logger.error(f"Redis get index keys error for {index_name}: {e}")
            return []
    
    async def invalidate_index(self, index_name: str) -> int:
        """Invalidate all keys in index set"""
        if not self.redis_client:
            return 0
        
        try:
            keys = await self.get_index_keys(index_name)
            if not keys:
                return 0
            
            # Delete all keys in the index
            deleted_count = 0
            for key in keys:
                result = await self.delete(key)
                if result:
                    deleted_count += 1
            
            # Clear the index set
            await self.redis_client.delete(index_name)
            return deleted_count
        except Exception as e:
            logger.error(f"Redis invalidate index error for {index_name}: {e}")
            return 0


class DistributedLock:
    """Distributed lock using Redis with Lua scripts"""
    
    def __init__(self, redis_client: redis.Redis, key: str, timeout: int = 30):
        self.redis_client = redis_client
        self.key = f"lock:{key}"
        self.timeout = timeout
        self.identifier = str(uuid.uuid4())
        self.acquired = False
    
    async def acquire(self) -> bool:
        """Acquire lock with timeout"""
        if self.acquired:
            return True
        
        # Lua script for atomic lock acquisition
        lua_script = """
        if redis.call("GET", KEYS[1]) == false then
            redis.call("SET", KEYS[1], ARGV[1])
            redis.call("EXPIRE", KEYS[1], ARGV[2])
            return 1
        else
            return 0
        end
        """
        
        try:
            result = await self.redis_client.eval(
                lua_script, 1, self.key, self.identifier, self.timeout
            )
            self.acquired = result == 1
            return self.acquired
        except Exception as e:
            logger.error(f"Redis lock acquire error for {self.key}: {e}")
            return False
    
    async def release(self) -> bool:
        """Release lock (only by the owner)"""
        if not self.acquired:
            return True
        
        # Lua script for atomic lock release
        lua_script = """
        if redis.call("GET", KEYS[1]) == ARGV[1] then
            redis.call("DEL", KEYS[1])
            return 1
        else
            return 0
        end
        """
        
        try:
            result = await self.redis_client.eval(
                lua_script, 1, self.key, self.identifier
            )
            self.acquired = result == 0
            return result == 1
        except Exception as e:
            logger.error(f"Redis lock release error for {self.key}: {e}")
            return False
    
    async def extend(self, additional_time: int) -> bool:
        """Extend lock timeout"""
        if not self.acquired:
            return False
        
        # Lua script for atomic lock extension
        lua_script = """
        if redis.call("GET", KEYS[1]) == ARGV[1] then
            redis.call("EXPIRE", KEYS[1], ARGV[2])
            return 1
        else
            return 0
        end
        """
        
        try:
            result = await self.redis_client.eval(
                lua_script, 1, self.key, self.identifier, self.timeout + additional_time
            )
            return result == 1
        except Exception as e:
            logger.error(f"Redis lock extend error for {self.key}: {e}")
            return False
    
    async def __aenter__(self):
        """Async context manager entry"""
        await self.acquire()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        await self.release()


# Global cache instance
_cache: Optional[RedisCache] = None

async def get_cache() -> RedisCache:
    """Get global cache instance"""
    global _cache
    if _cache is None:
        _cache = RedisCache()
        await _cache.connect()
    return _cache

async def get_distributed_lock(key: str, timeout: int = 30) -> DistributedLock:
    """Get distributed lock instance"""
    cache = await get_cache()
    return DistributedLock(cache.redis_client, key, timeout)


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


def cache_invalidate(pattern: str):
    """Decorator for invalidating cache after function execution"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            
            # Invalidate cache
            cache = await get_cache()
            await cache.delete_pattern(pattern)
            
            return result
        return wrapper
    return decorator