import json
import pickle
from typing import Any, Optional, Union, Callable, List
from datetime import datetime, timedelta
from functools import wraps
from .redis import redis_manager, RedisUtils
from .logging import get_logger

logger = get_logger(__name__)

class CacheManager:
    """Redis cache manager with JSON serialization and async support"""
    
    def __init__(self, default_ttl: int = 3600):
        self.default_ttl = default_ttl
        self._redis_manager = redis_manager
    
    def _serialize(self, value: Any) -> str:
        """Serialize value to JSON string"""
        return RedisUtils.serialize(value)
    
    def _deserialize(self, value: str) -> Any:
        """Deserialize JSON string to value"""
        return RedisUtils.deserialize(value)
    
    # Sync methods
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache (sync)"""
        try:
            redis_client = self._redis_manager.get_sync_redis()
            value = redis_client.get(key)
            if value is None:
                return None
            return self._deserialize(value)
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache with TTL (sync)"""
        try:
            redis_client = self._redis_manager.get_sync_redis()
            serialized_value = self._serialize(value)
            ttl = ttl or self.default_ttl
            return bool(redis_client.setex(key, ttl, serialized_value))
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Delete key from cache (sync)"""
        try:
            redis_client = self._redis_manager.get_sync_redis()
            return bool(redis_client.delete(key))
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """Check if key exists in cache (sync)"""
        try:
            redis_client = self._redis_manager.get_sync_redis()
            return bool(redis_client.exists(key))
        except Exception as e:
            logger.error(f"Cache exists error for key {key}: {e}")
            return False
    
    def get_or_set(self, key: str, factory_func: Callable, ttl: Optional[int] = None, *args, **kwargs) -> Any:
        """Get value from cache or set it using factory function (sync)"""
        value = self.get(key)
        if value is not None:
            return value
        
        # Generate value using factory function
        value = factory_func(*args, **kwargs)
        self.set(key, value, ttl)
        return value
    
    def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate all keys matching pattern (sync)"""
        try:
            redis_client = self._redis_manager.get_sync_redis()
            keys = redis_client.keys(pattern)
            if keys:
                return redis_client.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"Cache pattern invalidation error for {pattern}: {e}")
            return 0
    
    # Async methods
    async def get_async(self, key: str) -> Optional[Any]:
        """Get value from cache (async)"""
        try:
            redis_client = self._redis_manager.get_async_redis()
            value = await redis_client.get(key)
            if value is None:
                return None
            return self._deserialize(value)
        except Exception as e:
            logger.error(f"Async cache get error for key {key}: {e}")
            return None
    
    async def set_async(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache with TTL (async)"""
        try:
            redis_client = self._redis_manager.get_async_redis()
            serialized_value = self._serialize(value)
            ttl = ttl or self.default_ttl
            return await redis_client.setex(key, ttl, serialized_value)
        except Exception as e:
            logger.error(f"Async cache set error for key {key}: {e}")
            return False
    
    async def delete_async(self, key: str) -> bool:
        """Delete key from cache (async)"""
        try:
            redis_client = self._redis_manager.get_async_redis()
            result = await redis_client.delete(key)
            return bool(result)
        except Exception as e:
            logger.error(f"Async cache delete error for key {key}: {e}")
            return False
    
    async def exists_async(self, key: str) -> bool:
        """Check if key exists in cache (async)"""
        try:
            redis_client = self._redis_manager.get_async_redis()
            result = await redis_client.exists(key)
            return bool(result)
        except Exception as e:
            logger.error(f"Async cache exists error for key {key}: {e}")
            return False
    
    async def get_or_set_async(self, key: str, factory_func: Callable, ttl: Optional[int] = None, *args, **kwargs) -> Any:
        """Get value from cache or set it using factory function (async)"""
        value = await self.get_async(key)
        if value is not None:
            return value
        
        # Generate value using factory function
        if asyncio.iscoroutinefunction(factory_func):
            value = await factory_func(*args, **kwargs)
        else:
            value = factory_func(*args, **kwargs)
        await self.set_async(key, value, ttl)
        return value
    
    async def invalidate_pattern_async(self, pattern: str) -> int:
        """Invalidate all keys matching pattern (async)"""
        try:
            redis_client = self._redis_manager.get_async_redis()
            keys = await redis_client.keys(pattern)
            if keys:
                return await redis_client.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"Async cache pattern invalidation error for {pattern}: {e}")
            return 0

# Global cache instance
cache = CacheManager()

# Cache decorators
def cached(ttl: int = 3600, key_prefix: str = ""):
    """Decorator for caching function results (sync)"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = f"{key_prefix}:{func.__name__}:{hash(str(args) + str(sorted(kwargs.items())))}"
            
            # Try to get from cache
            result = cache.get(cache_key)
            if result is not None:
                return result
            
            # Execute function and cache result
            result = func(*args, **kwargs)
            cache.set(cache_key, result, ttl)
            return result
        
        return wrapper
    return decorator

def cached_async(ttl: int = 3600, key_prefix: str = ""):
    """Decorator for caching async function results"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = f"{key_prefix}:{func.__name__}:{hash(str(args) + str(sorted(kwargs.items())))}"
            
            # Try to get from cache
            result = await cache.get_async(cache_key)
            if result is not None:
                return result
            
            # Execute function and cache result
            result = await func(*args, **kwargs)
            await cache.set_async(cache_key, result, ttl)
            return result
        
        return wrapper
    return decorator

def cache_invalidate(pattern: str):
    """Decorator for invalidating cache after function execution (sync)"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            cache.invalidate_pattern(pattern)
            return result
        return wrapper
    return decorator

def cache_invalidate_async(pattern: str):
    """Decorator for invalidating cache after async function execution"""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            await cache.invalidate_pattern_async(pattern)
            return result
        return wrapper
    return decorator

# Cache key generators
def chat_key(chat_id: str) -> str:
    return f"chat:{chat_id}"

def chat_messages_key(chat_id: str, limit: int = 50, cursor: str = None) -> str:
    cursor_part = f":{cursor}" if cursor else ""
    return f"chat_messages:{chat_id}:{limit}{cursor_part}"

def rag_document_key(doc_id: str) -> str:
    return f"rag_document:{doc_id}"

def rag_documents_key(page: int, size: int, status: str = None, search: str = None) -> str:
    status_part = f":{status}" if status else ""
    search_part = f":{search}" if search else ""
    return f"rag_documents:{page}:{size}{status_part}{search_part}"

def rag_metrics_key() -> str:
    return "rag_metrics"

def user_chats_key(user_id: str) -> str:
    return f"user_chats:{user_id}"

def user_session_key(user_id: str) -> str:
    return f"user:session:{user_id}"

def rate_limit_key(identifier: str, action: str) -> str:
    return f"rate_limit:{action}:{identifier}"

# Import asyncio for async decorators
import asyncio