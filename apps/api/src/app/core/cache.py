"""
Cache manager для Redis операций.
"""
import json
from typing import Any, Optional, List
from datetime import datetime, timedelta


class CacheManager:
    """Менеджер кеширования для Redis."""
    
    def __init__(self, redis_client):
        self.redis = redis_client
    
    async def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """Установить значение в кеш."""
        try:
            serialized_value = json.dumps(value, default=str)
            await self.redis.setex(key, ttl, serialized_value)
            return True
        except Exception:
            return False
    
    async def get(self, key: str) -> Optional[Any]:
        """Получить значение из кеша."""
        try:
            value = await self.redis.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception:
            return None
    
    async def delete(self, key: str) -> bool:
        """Удалить значение из кеша."""
        try:
            await self.redis.delete(key)
            return True
        except Exception:
            return False
    
    async def exists(self, key: str) -> bool:
        """Проверить существование ключа."""
        try:
            return await self.redis.exists(key) > 0
        except Exception:
            return False
    
    async def keys(self, pattern: str) -> List[str]:
        """Получить все ключи по паттерну."""
        try:
            return await self.redis.keys(pattern)
        except Exception:
            return []
    
    async def delete_pattern(self, pattern: str) -> int:
        """Удалить все ключи по паттерну."""
        try:
            keys = await self.redis.keys(pattern)
            if keys:
                return await self.redis.delete(*keys)
            return 0
        except Exception:
            return 0


class SessionManager:
    """Менеджер сессий для Redis."""
    
    def __init__(self, redis_client):
        self.redis = redis_client
    
    async def create_session(self, user_id: str, session_data: dict) -> str:
        """Создать сессию."""
        session_id = f"session:{user_id}:{datetime.now().timestamp()}"
        await self.redis.setex(session_id, 3600, json.dumps(session_data, default=str))
        return session_id
    
    async def get_session(self, session_id: str) -> Optional[dict]:
        """Получить сессию."""
        try:
            data = await self.redis.get(session_id)
            if data:
                return json.loads(data)
            return None
        except Exception:
            return None
    
    async def update_session(self, session_id: str, update_data: dict) -> bool:
        """Обновить сессию."""
        try:
            session_data = await self.get_session(session_id)
            if session_data:
                session_data.update(update_data)
                await self.redis.setex(session_id, 3600, json.dumps(session_data, default=str))
                return True
            return False
        except Exception:
            return False
    
    async def delete_session(self, session_id: str) -> bool:
        """Удалить сессию."""
        try:
            await self.redis.delete(session_id)
            return True
        except Exception:
            return False


class RateLimiter:
    """Ограничитель скорости запросов."""
    
    def __init__(self, redis_client):
        self.redis = redis_client
    
    async def is_allowed(self, user_id: str, limit: int, window: int) -> bool:
        """Проверить, разрешен ли запрос."""
        try:
            key = f"rate_limit:{user_id}"
            current = await self.redis.incr(key)
            
            if current == 1:
                await self.redis.expire(key, window)
            
            return current <= limit
        except Exception:
            return True  # В случае ошибки разрешаем запрос


class DistributedLock:
    """Распределенная блокировка."""
    
    def __init__(self, redis_client):
        self.redis = redis_client
    
    async def acquire(self, lock_key: str, timeout: int = 10) -> Optional[str]:
        """Получить блокировку."""
        try:
            lock_id = f"{lock_key}:{datetime.now().timestamp()}"
            result = await self.redis.set(lock_key, lock_id, nx=True, ex=timeout)
            return lock_id if result else None
        except Exception:
            return None
    
    async def release(self, lock_key: str, lock_id: str) -> bool:
        """Освободить блокировку."""
        try:
            # Проверяем, что блокировка принадлежит нам
            current_lock = await self.redis.get(lock_key)
            if current_lock == lock_id:
                await self.redis.delete(lock_key)
                return True
            return False
        except Exception:
            return False
