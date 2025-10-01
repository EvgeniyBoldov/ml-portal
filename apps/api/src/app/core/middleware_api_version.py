from __future__ import annotations
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

class ApiVersionHeaderMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, version: str = "v1"):
        super().__init__(app)
        self.version = version

    async def dispatch(self, request: Request, call_next):
        resp = await call_next(request)
        resp.headers.setdefault("X-API-Version", self.version)
        return resp
