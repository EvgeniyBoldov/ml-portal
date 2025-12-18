"""
Rate Limiting for MCP endpoints.

Uses Redis for distributed rate limiting with sliding window algorithm.
"""
from __future__ import annotations
import logging
import time
from typing import Optional, Tuple
from fastapi import HTTPException, Request, Depends
from redis.asyncio import Redis

from app.api.deps import get_redis

logger = logging.getLogger(__name__)

# Default rate limits
DEFAULT_REQUESTS_PER_MINUTE = 60
DEFAULT_REQUESTS_PER_HOUR = 1000

# Rate limit by endpoint type
RATE_LIMITS = {
    "tools/call": {"rpm": 30, "rph": 500},  # Tool calls are expensive
    "chat/completions": {"rpm": 20, "rph": 300},  # LLM proxy is most expensive
    "default": {"rpm": 60, "rph": 1000},  # Other endpoints
}


class RateLimiter:
    """
    Redis-based rate limiter using sliding window.
    
    Usage:
        limiter = RateLimiter(redis)
        allowed, retry_after = await limiter.check("user:123", "tools/call")
        if not allowed:
            raise HTTPException(429, f"Rate limit exceeded. Retry after {retry_after}s")
    """
    
    def __init__(self, redis: Redis):
        self.redis = redis
    
    async def check(
        self,
        key: str,
        endpoint: str = "default",
    ) -> Tuple[bool, Optional[int]]:
        """
        Check if request is allowed under rate limit.
        
        Args:
            key: Unique identifier (e.g., "user:{user_id}" or "ip:{ip}")
            endpoint: Endpoint type for rate limit lookup
            
        Returns:
            Tuple of (allowed: bool, retry_after_seconds: Optional[int])
        """
        limits = RATE_LIMITS.get(endpoint, RATE_LIMITS["default"])
        rpm = limits["rpm"]
        rph = limits["rph"]
        
        now = int(time.time())
        minute_key = f"ratelimit:{key}:minute:{now // 60}"
        hour_key = f"ratelimit:{key}:hour:{now // 3600}"
        
        try:
            # Check minute limit
            minute_count = await self.redis.incr(minute_key)
            if minute_count == 1:
                await self.redis.expire(minute_key, 60)
            
            if minute_count > rpm:
                retry_after = 60 - (now % 60)
                logger.warning(f"Rate limit exceeded (minute) for {key}: {minute_count}/{rpm}")
                return False, retry_after
            
            # Check hour limit
            hour_count = await self.redis.incr(hour_key)
            if hour_count == 1:
                await self.redis.expire(hour_key, 3600)
            
            if hour_count > rph:
                retry_after = 3600 - (now % 3600)
                logger.warning(f"Rate limit exceeded (hour) for {key}: {hour_count}/{rph}")
                return False, retry_after
            
            return True, None
            
        except Exception as e:
            # If Redis fails, allow the request (fail open)
            logger.error(f"Rate limit check failed: {e}")
            return True, None
    
    async def get_usage(self, key: str) -> dict:
        """Get current usage stats for a key."""
        now = int(time.time())
        minute_key = f"ratelimit:{key}:minute:{now // 60}"
        hour_key = f"ratelimit:{key}:hour:{now // 3600}"
        
        try:
            minute_count = await self.redis.get(minute_key)
            hour_count = await self.redis.get(hour_key)
            
            return {
                "minute": int(minute_count) if minute_count else 0,
                "hour": int(hour_count) if hour_count else 0,
            }
        except Exception:
            return {"minute": 0, "hour": 0}


async def check_rate_limit(
    request: Request,
    redis: Redis = Depends(get_redis),
) -> None:
    """
    FastAPI dependency for rate limiting.
    
    Raises HTTPException 429 if rate limit exceeded.
    """
    # Get user identifier
    # Priority: user_id from auth > IP address
    user_id = None
    if hasattr(request.state, "user") and request.state.user:
        user_id = request.state.user.id
    
    if user_id:
        key = f"user:{user_id}"
    else:
        ip = request.client.host if request.client else "unknown"
        key = f"ip:{ip}"
    
    # Determine endpoint type from path
    path = request.url.path
    if "tools/call" in path or "tools%2Fcall" in path:
        endpoint = "tools/call"
    elif "chat/completions" in path:
        endpoint = "chat/completions"
    else:
        endpoint = "default"
    
    limiter = RateLimiter(redis)
    allowed, retry_after = await limiter.check(key, endpoint)
    
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Retry after {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )
