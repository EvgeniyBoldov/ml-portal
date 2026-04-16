from __future__ import annotations

import asyncio
import os
import time
import uuid
from typing import Optional

from fastapi import Request, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.logging import get_logger
from app.core.security import decode_jwt
from app.core.config import get_settings
from app.core.redis import get_redis

_REQUEST_ID_CTX_KEY = "request_id"
logger = get_logger(__name__)


def get_request_id(request: Optional[Request] = None) -> str | None:
    if request and hasattr(request.state, _REQUEST_ID_CTX_KEY):
        return getattr(request.state, _REQUEST_ID_CTX_KEY)
    return None


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.request_id = request.headers.get("X-Request-Id") or str(uuid.uuid4())
        request.state.tenant_id = request.headers.get("X-Tenant-Id")
        response = await call_next(request)
        response.headers["X-Request-Id"] = request.state.request_id
        return response


class TimeoutMiddleware(BaseHTTPMiddleware):
    """Cancel non-streaming requests that exceed configured timeout."""

    _STREAM_PATHS = ("/stream", "/sse", "/events")

    def __init__(self, app, timeout_seconds: float | None = None) -> None:
        super().__init__(app)
        self.timeout_seconds = timeout_seconds or float(
            os.getenv("HTTP_REQUEST_TIMEOUT_SECONDS", "120")
        )

    def _is_streaming(self, path: str) -> bool:
        return any(seg in path for seg in self._STREAM_PATHS)

    async def dispatch(self, request: Request, call_next):
        if self._is_streaming(request.url.path):
            return await call_next(request)
        try:
            return await asyncio.wait_for(call_next(request), timeout=self.timeout_seconds)
        except asyncio.TimeoutError:
            logger.warning(
                "Request timeout after %.0fs: %s %s",
                self.timeout_seconds,
                request.method,
                request.url.path,
            )
            return JSONResponse(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                content={"detail": f"Request timed out after {self.timeout_seconds:.0f}s"},
            )


class StartupReadinessMiddleware(BaseHTTPMiddleware):
    """Reject non-health requests until startup tasks are complete."""

    _ALLOW_PATH_PREFIXES = (
        "/healthz",
        "/readyz",
        "/api/v1/healthz",
        "/api/v1/readyz",
        "/api/v1/version",
        "/version",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/metrics",
    )

    async def dispatch(self, request: Request, call_next):
        path = request.url.path or ""
        if any(path.startswith(prefix) for prefix in self._ALLOW_PATH_PREFIXES):
            return await call_next(request)
        from app.core.db import is_startup_ready

        if not is_startup_ready():
            return JSONResponse(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                content={"detail": "Service is starting up, retry shortly"},
            )
        return await call_next(request)


class GlobalRateLimitMiddleware(BaseHTTPMiddleware):
    """Global fallback rate limiter for API requests."""

    _EXCLUDE_PREFIXES = (
        "/healthz",
        "/readyz",
        "/api/v1/healthz",
        "/api/v1/readyz",
        "/api/v1/version",
        "/version",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/metrics",
    )

    def __init__(self, app):
        super().__init__(app)
        settings = get_settings()
        self.enabled = bool(getattr(settings, "GLOBAL_RATE_LIMIT_ENABLED", True))
        self.rpm = int(max(getattr(settings, "GLOBAL_RATE_LIMIT_RPM", 240), 1))
        self.rph = int(max(getattr(settings, "GLOBAL_RATE_LIMIT_RPH", 2400), 1))

    async def dispatch(self, request: Request, call_next):
        path = request.url.path or ""
        if not self.enabled or any(path.startswith(prefix) for prefix in self._EXCLUDE_PREFIXES):
            return await call_next(request)
        if request.method == "OPTIONS":
            return await call_next(request)

        now = int(time.time())
        ip = request.client.host if request.client else "unknown"
        minute_key = f"ratelimit:global:ip:{ip}:minute:{now // 60}"
        hour_key = f"ratelimit:global:ip:{ip}:hour:{now // 3600}"
        try:
            redis = get_redis()
            minute_count = await redis.incr(minute_key)
            if minute_count == 1:
                await redis.expire(minute_key, 60)
            if minute_count > self.rpm:
                retry_after = 60 - (now % 60)
                return JSONResponse(
                    status_code=429,
                    content={"detail": f"Rate limit exceeded. Retry after {retry_after} seconds."},
                    headers={"Retry-After": str(retry_after)},
                )

            hour_count = await redis.incr(hour_key)
            if hour_count == 1:
                await redis.expire(hour_key, 3600)
            if hour_count > self.rph:
                retry_after = 3600 - (now % 3600)
                return JSONResponse(
                    status_code=429,
                    content={"detail": f"Rate limit exceeded. Retry after {retry_after} seconds."},
                    headers={"Retry-After": str(retry_after)},
                )
        except Exception:
            # Fail-open fallback for platform availability.
            pass
        return await call_next(request)


class TenantMiddleware(BaseHTTPMiddleware):
    """Middleware to resolve tenant from header or JWT for protected API paths."""

    def __init__(self, app, exclude_paths: list[str] | None = None):
        super().__init__(app)
        self.exclude_paths = exclude_paths or [
            "/docs",
            "/redoc",
            "/openapi.json",
            "/auth/login",
            "/auth/refresh",
            "/auth/.well-known/jwks.json",
            "/health",
            "/metrics",
        ]

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.exclude_paths:
            return await call_next(request)

        tenant_id = request.headers.get("X-Tenant-Id")
        if tenant_id:
            tenant_id = tenant_id.strip()

        if not tenant_id:
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                try:
                    payload = decode_jwt(auth_header.split(" ", 1)[1])
                    tenant_ids = payload.get("tenant_ids", []) or []
                    if tenant_ids:
                        tenant_id = str(tenant_ids[0])
                except Exception as exc:
                    logger.warning("Failed to extract tenant from JWT: %s", exc)
            else:
                # Cookie-based auth path (SSE/web apps) — align with get_current_user().
                access_cookie = request.cookies.get("access_token")
                if access_cookie:
                    try:
                        payload = decode_jwt(access_cookie)
                        tenant_ids = payload.get("tenant_ids", []) or []
                        if tenant_ids:
                            tenant_id = str(tenant_ids[0])
                    except Exception as exc:
                        logger.warning("Failed to extract tenant from access_token cookie: %s", exc)

        if tenant_id:
            try:
                import uuid as _uuid

                _uuid.UUID(str(tenant_id))
            except ValueError:
                return JSONResponse(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    content={"detail": "Invalid tenant ID format"},
                )

        request.state.tenant_id = tenant_id

        if not tenant_id and self._is_protected_endpoint(request.url.path):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"detail": "Tenant ID required"},
            )

        response = await call_next(request)
        return response

    @staticmethod
    def _is_protected_endpoint(path: str) -> bool:
        protected_prefixes = (
            "/api/v1/chats",
            "/api/v1/users",
            "/api/v1/rag",
            "/api/v1/artifacts",
        )
        return any(path.startswith(prefix) for prefix in protected_prefixes)


class TracingMiddleware(BaseHTTPMiddleware):
    """Middleware for adding trace IDs to requests."""

    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("X-Trace-ID") or str(uuid.uuid4())
        span_id = str(uuid.uuid4())

        request.state.trace_id = trace_id
        request.state.span_id = span_id

        response = await call_next(request)

        response.headers["X-Trace-ID"] = trace_id
        response.headers["X-Span-ID"] = span_id

        return response


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Middleware for handling idempotency keys."""

    async def dispatch(self, request: Request, call_next):
        idempotency_key = request.headers.get("Idempotency-Key")
        if idempotency_key and request.method in ["POST", "PUT", "PATCH"]:
            pass
        response = await call_next(request)
        return response
