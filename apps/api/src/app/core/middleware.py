from __future__ import annotations
import uuid
from contextvars import ContextVar
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_request_id: ContextVar[str] = ContextVar("_request_id", default="-")

def get_request_id(request: Request | None = None) -> str:
    if request is not None:
        return request.headers.get("X-Request-ID") or _request_id.get()
    return _request_id.get()

class RequestIDMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, header_name: str = "X-Request-ID"):
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get(self.header_name) or str(uuid.uuid4())
        token = _request_id.set(rid)
        try:
            resp: Response = await call_next(request)
            resp.headers.setdefault(self.header_name, rid)
            return resp
        finally:
            _request_id.reset(token)
