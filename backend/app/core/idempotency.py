from starlette.middleware.base import BaseHTTPMiddleware
class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        return await call_next(request)
