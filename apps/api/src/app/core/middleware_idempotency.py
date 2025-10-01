"""
app/core/middleware_idempotency.py
UUIDv4-only Idempotency-Key with safe caching; skips /api/v1/auth/*.
"""
from __future__ import annotations
import re
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

UUID_V4_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.I)

SENSITIVE_PREFIXES = ("/api/v1/auth/",)

class IdempotencyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, storage):
        super().__init__(app); self.storage = storage

    async def dispatch(self, request, call_next):
        if request.method not in {"POST","PUT","PATCH","DELETE"}:
            return await call_next(request)
        if any(request.url.path.startswith(p) for p in SENSITIVE_PREFIXES):
            return await call_next(request)

        key = request.headers.get("Idempotency-Key")
        if not key or not UUID_V4_RE.match(key):
            return Response(
                content=(b'{"type":"about:blank","title":"Invalid Idempotency-Key","status":400,"detail":"Use UUIDv4"}'),
                status_code=400, media_type="application/problem+json"
            )

        cache_key = f"idemp:{key}"
        cached = await self.storage.get(cache_key)
        if cached:
            resp = Response(content=cached)
            resp.headers["Content-Type"] = "application/json"
            resp.headers["Cache-Control"] = "no-store"
            resp.headers["X-Idempotent-Replay"] = "true"
            return resp

        resp: Response = await call_next(request)
        if (200 <= resp.status_code < 300
            and resp.headers.get("content-type","").startswith("application/json")
            and (resp.body is not None) and len(resp.body) < 1024*1024):
            await self.storage.setex(cache_key, 60*60*24, resp.body)
        return resp
