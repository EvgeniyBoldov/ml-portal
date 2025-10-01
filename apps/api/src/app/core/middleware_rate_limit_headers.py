from __future__ import annotations
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

class RateLimitHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        resp = await call_next(request)
        hdrs = getattr(request.state, "rate_limit_headers", None)
        if isinstance(hdrs, dict):
            for k, v in hdrs.items():
                resp.headers.setdefault(k, str(v))
        return resp
