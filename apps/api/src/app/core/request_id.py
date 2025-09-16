"""
Request ID middleware для трассировки запросов
"""
import uuid
from contextvars import ContextVar
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

# Context variable для хранения request ID
request_id_ctx: ContextVar[str] = ContextVar('request_id', default=None)

class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware для генерации и передачи request ID"""
    
    async def dispatch(self, request: Request, call_next):
        # Генерируем или получаем request ID
        request_id = request.headers.get('X-Request-ID') or str(uuid.uuid4())
        
        # Сохраняем в контекст
        request_id_ctx.set(request_id)
        
        # Обрабатываем запрос
        response = await call_next(request)
        
        # Добавляем request ID в заголовки ответа
        response.headers['X-Request-ID'] = request_id
        
        return response

def get_request_id() -> str:
    """Получить текущий request ID"""
    return request_id_ctx.get() or "unknown"
