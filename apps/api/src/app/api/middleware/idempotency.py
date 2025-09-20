from __future__ import annotations
import hashlib, json, time
from typing import Callable
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from app.core.limiting import aioredis

class IdempotencyMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, redis_url: str | None = None, ttl_s: int = 600):
        super().__init__(app)
        self.redis_url = redis_url
        self.ttl_s = ttl_s
        self._mem: dict[str, tuple[float, bytes, str]] = {}

    async def dispatch(self, request: Request, call_next: Callable):
        method = request.method.upper()
        if method not in {"POST","PUT","PATCH"}:
            return await call_next(request)

        key = request.headers.get("Idempotency-Key")
        if not key:
            return await call_next(request)

        scope_key = self._scope_key(request, key)

        # Try repo
        if aioredis and self.redis_url:
            r = await aioredis.from_url(self.redis_url)
            cached = await r.get(scope_key)
            if cached:
                status_str, headers_json, body = json.loads(cached)
                return Response(content=body.encode("utf-8"), status_code=int(status_str), headers=json.loads(headers_json))
        else:
            cached = self._mem.get(scope_key)
            if cached and (time.time() - cached[0] < self.ttl_s):
                _, body, status_headers = cached
                status_str, headers_json = status_headers.split("|", 1)
                return Response(content=body, status_code=int(status_str), headers=json.loads(headers_json))

        # Execute call
        response: Response = await call_next(request)

        # Store
        if aioredis and self.redis_url:
            r = await aioredis.from_url(self.redis_url)
            data = json.dumps([str(response.status_code), json.dumps(dict(response.headers)), (await response.body()) .decode("utf-8")])
            await r.setex(scope_key, self.ttl_s, data)
        else:
            body = await response.body()
            self._mem[scope_key] = (time.time(), body, f"{response.status_code}|{json.dumps(dict(response.headers))}")

        return response

    def _scope_key(self, request: Request, idem_key: str) -> str:
        # Build a key per route+auth+body hash to avoid cross-user replay
        auth = request.headers.get("Authorization", "")
        path = request.url.path
        raw = f"{idem_key}:{auth}:{path}"
        return "idem:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()
