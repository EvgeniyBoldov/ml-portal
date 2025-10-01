from __future__ import annotations
from typing import Optional, Any, Union
import json
import pickle
from redis.asyncio import Redis
from redis import Redis as SyncRedis
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

# Global Redis instances
_redis: Optional[Redis] = None
_sync_redis: Optional[SyncRedis] = None

class RedisManager:
    """Redis connection manager with both sync and async support"""
    
    def __init__(self):
        self._async_redis: Optional[Redis] = None
        self._sync_redis: Optional[SyncRedis] = None
    
    def get_async_redis(self) -> Redis:
        """Get async Redis client"""
        if self._async_redis is None:
            s = get_settings()
            self._async_redis = Redis.from_url(
                s.REDIS_URL,
                decode_responses=True,
                retry_on_timeout=True,
                socket_keepalive=True,
                socket_keepalive_options={}
            )
        return self._async_redis
    
    def get_sync_redis(self) -> SyncRedis:
        """Get sync Redis client"""
        if self._sync_redis is None:
            s = get_settings()
            self._sync_redis = SyncRedis.from_url(
                s.REDIS_URL,
                decode_responses=True,
                retry_on_timeout=True,
                socket_keepalive=True,
                socket_keepalive_options={}
            )
        return self._sync_redis
    
    async def ping_async(self) -> bool:
        """Ping async Redis connection"""
        try:
            redis_client = self.get_async_redis()
            result = await redis_client.ping()
            return result
        except Exception as e:
            logger.error(f"Async Redis ping failed: {e}")
            return False
    
    def ping_sync(self) -> bool:
        """Ping sync Redis connection"""
        try:
            redis_client = self.get_sync_redis()
            result = redis_client.ping()
            return result
        except Exception as e:
            logger.error(f"Sync Redis ping failed: {e}")
            return False
    
    async def close_async(self) -> None:
        """Close async Redis connection"""
        if self._async_redis:
            await self._async_redis.close()
            self._async_redis = None
            logger.info("Async Redis connection closed")
    
    def close_sync(self) -> None:
        """Close sync Redis connection"""
        if self._sync_redis:
            self._sync_redis.close()
            self._sync_redis = None
            logger.info("Sync Redis connection closed")
    
    async def health_check_async(self) -> bool:
        """Check async Redis connection health"""
        try:
            redis_client = self.get_async_redis()
            await redis_client.ping()
            return True
        except Exception as e:
            logger.error(f"Async Redis health check failed: {e}")
            return False
    
    def health_check_sync(self) -> bool:
        """Check sync Redis connection health"""
        try:
            redis_client = self.get_sync_redis()
            redis_client.ping()
            return True
        except Exception as e:
            logger.error(f"Sync Redis health check failed: {e}")
            return False

# Global Redis manager instance
redis_manager = RedisManager()

# Convenience functions for backward compatibility
def get_redis() -> Redis:
    """Get async Redis client (FastAPI dependency)"""
    return redis_manager.get_async_redis()

def get_sync_redis() -> SyncRedis:
    """Get sync Redis client"""
    return redis_manager.get_sync_redis()

def get_async_redis() -> Redis:
    """Get async Redis client"""
    return redis_manager.get_async_redis()

# Utility functions for common Redis operations
class RedisUtils:
    """Utility functions for Redis operations"""
    
    @staticmethod
    def serialize(value: Any) -> str:
        """Serialize value for Redis storage"""
        try:
            return json.dumps(value, default=str)
        except (TypeError, ValueError):
            # Fallback to pickle for complex objects
            return pickle.dumps(value).hex()
    
    @staticmethod
    def deserialize(value: str) -> Any:
        """Deserialize value from Redis storage"""
        try:
            return json.loads(value)
        except (TypeError, ValueError, json.JSONDecodeError):
            # Fallback to pickle for complex objects
            return pickle.loads(bytes.fromhex(value))
    
    @staticmethod
    def make_key(*parts: Union[str, int]) -> str:
        """Create Redis key from parts"""
        return ":".join(str(part) for part in parts)
    
    @staticmethod
    def make_pattern(*parts: Union[str, int]) -> str:
        """Create Redis pattern from parts"""
        return ":".join(str(part) for part in parts) + "*"

# Common Redis key patterns
class RedisKeys:
    """Common Redis key patterns"""
    
    @staticmethod
    def user_session(user_id: str) -> str:
        return f"user:session:{user_id}"
    
    @staticmethod
    def user_tokens(user_id: str) -> str:
        return f"user:tokens:{user_id}"
    
    @staticmethod
    def chat_messages(chat_id: str) -> str:
        return f"chat:messages:{chat_id}"
    
    @staticmethod
    def rag_document(doc_id: str) -> str:
        return f"rag:document:{doc_id}"
    
    @staticmethod
    def rate_limit(identifier: str, action: str) -> str:
        return f"rate_limit:{action}:{identifier}"
    
    @staticmethod
    def cache_key(prefix: str, *args) -> str:
        return f"cache:{prefix}:" + ":".join(str(arg) for arg in args)
