import json
import pickle
from typing import Any, Optional, Union
from datetime import datetime, timedelta
import redis
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

class CacheManager:
    """Redis cache manager with JSON serialization"""
    
    def __init__(self):
        self.redis_client = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True
        )
        self.default_ttl = 3600  # 1 hour
    
    def _serialize(self, value: Any) -> str:
        """Serialize value to JSON string"""
        try:
            return json.dumps(value, default=str)
        except (TypeError, ValueError):
            # Fallback to pickle for complex objects
            return pickle.dumps(value).hex()
    
    def _deserialize(self, value: str) -> Any:
        """Deserialize JSON string to value"""
        try:
            return json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            # Fallback to pickle for complex objects
            return pickle.loads(bytes.fromhex(value))
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        try:
            value = self.redis_client.get(key)
            if value is None:
                return None
            return self._deserialize(value)
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            return None
    
    def set(
        self, 
        key: str, 
        value: Any, 
        ttl: Optional[int] = None
    ) -> bool:
        """Set value in cache with TTL"""
        try:
            serialized_value = self._serialize(value)
            ttl = ttl or self.default_ttl
            return self.redis_client.setex(key, ttl, serialized_value)
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """Delete key from cache"""
        try:
            return bool(self.redis_client.delete(key))
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """Check if key exists in cache"""
        try:
            return bool(self.redis_client.exists(key))
        except Exception as e:
            logger.error(f"Cache exists error for key {key}: {e}")
            return False
    
    def get_or_set(
        self, 
        key: str, 
        factory_func, 
        ttl: Optional[int] = None,
        *args,
        **kwargs
    ) -> Any:
        """Get value from cache or set it using factory function"""
        value = self.get(key)
        if value is not None:
            return value
        
        # Generate value using factory function
        value = factory_func(*args, **kwargs)
        self.set(key, value, ttl)
        return value
    
    def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate all keys matching pattern"""
        try:
            keys = self.redis_client.keys(pattern)
            if keys:
                return self.redis_client.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"Cache pattern invalidation error for {pattern}: {e}")
            return 0

# Global cache instance
cache = CacheManager()

# Cache decorators
def cached(ttl: int = 3600, key_prefix: str = ""):
    """Decorator for caching function results"""
    def decorator(func):
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

def cache_invalidate(pattern: str):
    """Decorator for invalidating cache after function execution"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            result = func(*args, **kwargs)
            cache.invalidate_pattern(pattern)
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
