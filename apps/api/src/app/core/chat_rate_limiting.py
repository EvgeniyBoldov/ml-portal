"""
Rate limiting для чата
"""
import time
import json
from typing import Optional
from fastapi import Request, HTTPException
from app.core.config import settings
from app.core.redis import get_async_redis
import logging

logger = logging.getLogger(__name__)

class ChatRateLimiter:
    def __init__(self):
        self.rps = settings.CHAT_RATE_LIMIT_RPS
        self.burst = settings.CHAT_RATE_LIMIT_BURST
        self.window = 60  # 60 секунд
    
    async def check_rate_limit(self, request: Request, user_id: Optional[str] = None) -> bool:
        """
        Проверка rate limit для чата
        
        Args:
            request: FastAPI request
            user_id: ID пользователя (если есть)
        
        Returns:
            True если запрос разрешен, False если превышен лимит
        """
        try:
            # Определяем ключ для rate limiting
            if user_id:
                key = f"chat_rate_limit:user:{user_id}"
            else:
                # Fallback на IP
                client_ip = request.client.host
                key = f"chat_rate_limit:ip:{client_ip}"
            
            # Используем единый async Redis клиент
            redis_client = await get_async_redis()
            client = await redis_client.get_client()
            
            # Используем sliding window counter
            current_time = int(time.time())
            window_start = current_time - self.window
            
            # Удаляем старые записи
            await client.zremrangebyscore(key, 0, window_start)
            
            # Подсчитываем запросы в окне
            request_count = await client.zcard(key)
            
            if request_count >= self.burst:
                logger.warning(f"Rate limit exceeded for key {key}: {request_count}/{self.burst}")
                return False
            
            # Добавляем текущий запрос
            await client.zadd(key, {str(current_time): current_time})
            await client.expire(key, self.window)
            
            return True
            
        except Exception as e:
            logger.error(f"Rate limiting check failed: {e}")
            # В случае ошибки разрешаем запрос (fail open)
            return True
    
    async def get_retry_after(self, request: Request, user_id: Optional[str] = None) -> int:
        """Получение времени до следующего разрешенного запроса"""
        try:
            if user_id:
                key = f"chat_rate_limit:user:{user_id}"
            else:
                client_ip = request.client.host
                key = f"chat_rate_limit:ip:{client_ip}"
            
            # Используем единый async Redis клиент
            redis_client = await get_async_redis()
            client = await redis_client.get_client()
            
            # Получаем время самого старого запроса в окне
            oldest_requests = await client.zrange(key, 0, 0, withscores=True)
            if oldest_requests:
                oldest_time = int(oldest_requests[0][1])
                retry_after = oldest_time + self.window - int(time.time())
                return max(1, retry_after)
            
            return 1
            
        except Exception as e:
            logger.error(f"Failed to get retry after: {e}")
            return 60

# Глобальный экземпляр
chat_rate_limiter = ChatRateLimiter()

async def check_chat_rate_limit(request: Request, user_id: Optional[str] = None):
    """Middleware функция для проверки rate limit чата"""
    if not await chat_rate_limiter.check_rate_limit(request, user_id):
        retry_after = await chat_rate_limiter.get_retry_after(request, user_id)
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded for chat requests",
            headers={"Retry-After": str(retry_after)}
        )
