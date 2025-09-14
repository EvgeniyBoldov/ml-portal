"""
Security headers middleware для защиты от различных атак
"""
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import os

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Middleware для добавления защитных HTTP-заголовков"""
    
    def __init__(self, app, environment: str = "development"):
        super().__init__(app)
        self.environment = environment
    
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        
        # X-Frame-Options - защита от clickjacking
        response.headers["X-Frame-Options"] = "DENY"
        
        # X-Content-Type-Options - защита от MIME-sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # Referrer-Policy - контроль реферальной информации
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # X-XSS-Protection (устаревший, но для совместимости)
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # Strict-Transport-Security (только для HTTPS)
        if request.url.scheme == "https":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        
        # Content-Security-Policy (только в production)
        if self.environment == "production":
            csp = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https:; "
                "font-src 'self'; "
                "connect-src 'self'; "
                "frame-ancestors 'none';"
            )
            response.headers["Content-Security-Policy"] = csp
        else:
            # В development более мягкая политика
            response.headers["Content-Security-Policy"] = "default-src 'self' 'unsafe-inline' 'unsafe-eval'"
        
        # Permissions-Policy (новый стандарт)
        permissions = (
            "camera=(), "
            "microphone=(), "
            "geolocation=(), "
            "payment=(), "
            "usb=(), "
            "magnetometer=(), "
            "gyroscope=(), "
            "speaker=()"
        )
        response.headers["Permissions-Policy"] = permissions
        
        return response
