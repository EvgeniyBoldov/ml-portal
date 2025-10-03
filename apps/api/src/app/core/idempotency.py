from __future__ import annotations
import hashlib
import json
from typing import Any, Dict, Optional
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.config import get_settings
import redis
import logging

logger = logging.getLogger(__name__)

class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Middleware for idempotency key handling"""
    
    def __init__(self, app, redis_client: Optional[redis.Redis] = None):
        super().__init__(app)
        self.settings = get_settings()
        self.redis_client = redis_client or self._create_redis_client()
        self.ttl_seconds = self.settings.IDEMP_TTL_HOURS * 3600
        
        # Methods that should be idempotent
        self.idempotent_methods = {"POST", "PUT", "PATCH", "DELETE"}
        
        # Paths to exclude from idempotency
        self.exclude_paths = {
            "/docs", "/redoc", "/openapi.json", "/health", "/metrics",
            "/auth/login", "/auth/refresh", "/auth/logout"
        }
    
    def _create_redis_client(self) -> redis.Redis:
        """Create Redis client"""
        try:
            return redis.from_url(self.settings.REDIS_URL)
        except Exception as e:
            logger.warning(f"Failed to create Redis client: {e}")
            return None
    
    async def dispatch(self, request: Request, call_next):
        # Skip idempotency for excluded paths and methods
        if (request.url.path in self.exclude_paths or 
            request.method not in self.idempotent_methods):
            return await call_next(request)
        
        # Get idempotency key from header
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            return await call_next(request)
        
        # Validate idempotency key format
        if not self._is_valid_idempotency_key(idempotency_key):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"detail": "Invalid idempotency key format"}
            )
        
        # Check if we have a cached response
        if self.redis_client:
            cached_response = await self._get_cached_response(idempotency_key)
            if cached_response:
                logger.info(f"Returning cached response for idempotency key: {idempotency_key}")
                return JSONResponse(
                    status_code=cached_response["status_code"],
                    content=cached_response["content"],
                    headers=cached_response.get("headers", {})
                )
        
        # Process request
        response = await call_next(request)
        
        # Cache successful responses
        if (self.redis_client and 
            response.status_code < 400 and 
            response.status_code >= 200):
            await self._cache_response(idempotency_key, response)
        
        return response
    
    def _is_valid_idempotency_key(self, key: str) -> bool:
        """Validate idempotency key format"""
        # Basic validation: should be reasonable length and format
        if not key or len(key) < 1 or len(key) > 255:
            return False
        
        # Should not contain whitespace or special characters that could cause issues
        if any(c.isspace() for c in key):
            return False
        
        return True
    
    async def _get_cached_response(self, idempotency_key: str) -> Optional[Dict[str, Any]]:
        """Get cached response from Redis"""
        try:
            if not self.redis_client:
                return None
            key = f"idempotency:{idempotency_key}"
            cached_data = self.redis_client.get(key)
            if cached_data:
                return json.loads(cached_data)
        except Exception as e:
            logger.warning(f"Failed to get cached response: {e}")
        return None
    
    async def _cache_response(self, idempotency_key: str, response: Any):
        """Cache response in Redis"""
        try:
            # Get response body
            if hasattr(response, 'body'):
                body = response.body
            else:
                body = b""
            
            # Try to parse as JSON
            try:
                content = json.loads(body.decode()) if body else {}
            except:
                content = {"message": "Response cached but not JSON"}
            
            cache_data = {
                "status_code": response.status_code,
                "content": content,
                "headers": dict(response.headers) if hasattr(response, 'headers') else {}
            }
            
            key = f"idempotency:{idempotency_key}"
            self.redis_client.setex(
                key, 
                self.ttl_seconds, 
                json.dumps(cache_data)
            )
            
            logger.info(f"Cached response for idempotency key: {idempotency_key}")
            
        except Exception as e:
            logger.warning(f"Failed to cache response: {e}")

def create_idempotency_key_hash(request: Request) -> str:
    """Create hash from request for idempotency"""
    # Create hash from method, path, and body
    content = f"{request.method}:{request.url.path}"
    
    # Add body hash if present
    if hasattr(request, '_body'):
        body_hash = hashlib.sha256(request._body).hexdigest()[:16]
        content += f":{body_hash}"
    
    return hashlib.sha256(content.encode()).hexdigest()[:32]
