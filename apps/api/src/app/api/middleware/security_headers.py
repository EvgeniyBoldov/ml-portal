from __future__ import annotations
from typing import Callable, Dict
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, content_security_policy: str | None = None, hsts: bool = False):
        super().__init__(app)
        self.csp = content_security_policy
        self.hsts = hsts

    async def dispatch(self, request: Request, call_next: Callable):
        resp: Response = await call_next(request)
        headers: Dict[str, str] = {
            "X-Content-Type-Options": "nosniff",
            "X-Frame-Options": "DENY",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
        }
        if self.csp:
            headers["Content-Security-Policy"] = self.csp
        if self.hsts:
            headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        for k, v in headers.items():
            resp.headers.setdefault(k, v)
        return resp
