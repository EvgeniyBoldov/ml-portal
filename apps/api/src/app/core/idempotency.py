"""
Idempotency middleware for handling Idempotency-Key header
"""
from __future__ import annotations
from typing import Optional, Dict, Any
from fastapi import Request, Response, HTTPException, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse, StreamingResponse
import hashlib
import json
import time
from app.core.config import settings
from app.core.redis import get_redis
from app.core.errors import format_problem_payload
from app.core.middleware import get_request_id

class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Middleware for handling Idempotency-Key header"""
    
    def __init__(self, app):
        super().__init__(app)
        self.ttl_hours = getattr(settings, 'IDEMP_TTL_HOURS', 24)
        self.max_bytes = getattr(settings, 'IDEMPOTENCY_MAX_BYTES', 1024 * 1024)  # 1MB
        self.enabled = getattr(settings, 'IDEMPOTENCY_ENABLED', True)
    
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        """Process request with idempotency handling"""
        
        # Skip if idempotency is disabled
        if not self.enabled:
            return await call_next(request)
        
        # Only handle POST, PUT, PATCH requests
        if request.method not in ['POST', 'PUT', 'PATCH']:
            return await call_next(request)
        
        # Get idempotency key from header
        idempotency_key = request.headers.get('Idempotency-Key')
        if not idempotency_key:
            return await call_next(request)
        
        # Validate idempotency key format (should be UUID-like)
        if len(idempotency_key) < 10 or len(idempotency_key) > 100:
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content=format_problem_payload(
                    code="INVALID_IDEMPOTENCY_KEY",
                    message="Idempotency-Key must be 10-100 characters",
                    http_status=400
                )
            )
        
        # Normalize cache key (method + path + body hash)
        body_hash = ""
        body = None
        try:
            # Read request body for key normalization
            body = await request.body()
            if body:
                # Limit body size for key generation (first 1KB)
                body_sample = body[:1024]
                body_hash = hashlib.sha256(body_sample).hexdigest()[:16]
        except Exception:
            body_hash = "no_body"
        
        # Add user/tenant context to prevent collisions
        user_context = "anonymous"
        tenant_context = "default"
        
        # Try to extract user context from request
        try:
            # Check if user is authenticated (from middleware or headers)
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]
                # Decode token to get user ID (without full validation)
                import jwt
                try:
                    payload = jwt.decode(token, options={"verify_signature": False})
                    user_context = payload.get("sub", "unknown")
                    tenant_context = payload.get("tenant_id", "default")
                except:
                    pass
        except:
            pass
        
        cache_key = f"idempotency:{tenant_context}:{user_context}:{request.method}:{request.url.path}:{body_hash}:{idempotency_key}"
        
        # Create new request with restored body for downstream
        if body is not None:
            # Create a new request with the body restored
            from starlette.requests import Request as StarletteRequest
            from starlette.datastructures import Headers
            
            # Create a new receive function that returns the body
            async def receive_with_body():
                return {"type": "http.request", "body": body, "more_body": False}
            
            # Create new request with restored body
            request = StarletteRequest(request.scope, receive_with_body)
            request.state._body = body
        
        try:
            # Check Redis for existing response
            redis_client = get_redis()
            try:
                cached_response = await redis_client.get(cache_key)
            except Exception as e:
                # If Redis is unavailable or event loop is closed, skip caching
                print(f"Redis error in idempotency middleware: {e}")
                cached_response = None
            
            if cached_response:
                # Return cached response
                response_data = json.loads(cached_response)
                headers = response_data.get('headers', {})
                # Ensure Problem JSON format for error responses
                if response_data['status_code'] >= 400:
                    headers['Content-Type'] = 'application/problem+json'
                return JSONResponse(
                    status_code=response_data['status_code'],
                    content=response_data['content'],
                    headers=headers
                )
            
            # Process request
            response = await call_next(request)
            
            # Skip caching for streaming responses (SSE, WebSocket, etc.)
            if (response.media_type == "text/event-stream" or 
                isinstance(response, StreamingResponse)):
                return response
            
            # Cache successful responses (2xx status codes)
            if 200 <= response.status_code < 300:
                # Read response body
                response_body = b""
                async for chunk in response.body_iterator:
                    response_body += chunk
                
                # Check response size (limit to 256KB for caching)
                max_cache_size = min(self.max_bytes, 256 * 1024)  # 256KB
                if len(response_body) > max_cache_size:
                    # Response too large for caching, return without caching
                    return Response(
                        content=response_body,
                        status_code=response.status_code,
                        headers=dict(response.headers),
                        media_type=response.media_type
                    )
                
                # Prepare response data for caching
                response_data = {
                    'status_code': response.status_code,
                    'content': json.loads(response_body.decode()) if response_body else {},
                    'headers': dict(response.headers)
                }
                
                # Cache response
                try:
                    await redis_client.setex(
                        cache_key,
                        self.ttl_hours * 3600,  # Convert hours to seconds
                        json.dumps(response_data)
                    )
                except Exception as e:
                    # If Redis is unavailable, continue without caching
                    print(f"Redis cache error: {e}")
                
                # Return response with original body
                return Response(
                    content=response_body,
                    status_code=response.status_code,
                    headers=dict(response.headers),
                    media_type=response.media_type
                )
            
            # For non-2xx responses, don't cache but return as-is
            return response
            
        except Exception as e:
            # Log error and continue without idempotency
            print(f"Idempotency middleware error: {e}")
            return await call_next(request)