"""
Rate limiting middleware for authentication endpoints
"""
from __future__ import annotations
import time
from typing import Dict, Optional
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
import redis
from .config import settings

# Redis connection for rate limiting
redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)

def get_client_ip(request: Request) -> str:
    """Extract client IP from request, considering X-Forwarded-For header"""
    # Check for forwarded IP first (for load balancers/proxies)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # Take the first IP in the chain
        return forwarded_for.split(",")[0].strip()
    
    # Fall back to direct connection IP
    if hasattr(request, "client") and request.client:
        return request.client.host
    
    return "unknown"

def check_rate_limit(
    request: Request,
    key_prefix: str = "rate_limit",
    max_attempts: int = None,
    window_seconds: int = None
) -> bool:
    """
    Check if request is within rate limits
    
    Args:
        request: FastAPI request object
        key_prefix: Prefix for Redis key
        max_attempts: Maximum attempts per window (uses config if None)
        window_seconds: Time window in seconds (uses config if None)
    
    Returns:
        True if request is allowed, False if rate limited
    """
    if max_attempts is None:
        max_attempts = settings.RATE_LIMIT_LOGIN_ATTEMPTS
    if window_seconds is None:
        window_seconds = settings.RATE_LIMIT_LOGIN_WINDOW
    
    client_ip = get_client_ip(request)
    current_time = int(time.time())
    window_start = current_time - window_seconds
    
    # Create rate limit key
    rate_key = f"{key_prefix}:{client_ip}"
    
    try:
        # Use Redis pipeline for atomic operations
        pipe = redis_client.pipeline()
        
        # Remove expired entries
        pipe.zremrangebyscore(rate_key, 0, window_start)
        
        # Count current attempts
        pipe.zcard(rate_key)
        
        # Add current attempt
        pipe.zadd(rate_key, {str(current_time): current_time})
        
        # Set expiration
        pipe.expire(rate_key, window_seconds)
        
        results = pipe.execute()
        current_attempts = results[1]
        
        return current_attempts < max_attempts
        
    except Exception as e:
        # If Redis is unavailable, allow the request (fail open)
        print(f"Rate limiting error: {e}")
        return True

def rate_limit_middleware(
    max_attempts: int = None,
    window_seconds: int = None,
    key_prefix: str = "rate_limit"
):
    """
    Rate limiting decorator for endpoints
    
    Usage:
        @app.post("/auth/login")
        @rate_limit_middleware(max_attempts=5, window_seconds=300)
        async def login(...):
            ...
    """
    def decorator(func):
        async def wrapper(*args, **kwargs):
            # Find request object in args
            request = None
            for arg in args:
                if isinstance(arg, Request):
                    request = arg
                    break
            
            if not request:
                return await func(*args, **kwargs)
            
            if not check_rate_limit(request, key_prefix, max_attempts, window_seconds):
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={
                        "error": "rate_limit_exceeded",
                        "message": f"Too many requests. Try again in {window_seconds or settings.RATE_LIMIT_LOGIN_WINDOW} seconds.",
                        "retry_after": window_seconds or settings.RATE_LIMIT_LOGIN_WINDOW
                    }
                )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator

def clear_rate_limit(request: Request, key_prefix: str = "rate_limit") -> None:
    """Clear rate limit for a specific client (e.g., after successful login)"""
    client_ip = get_client_ip(request)
    rate_key = f"{key_prefix}:{client_ip}"
    
    try:
        redis_client.delete(rate_key)
    except Exception as e:
        print(f"Error clearing rate limit: {e}")
