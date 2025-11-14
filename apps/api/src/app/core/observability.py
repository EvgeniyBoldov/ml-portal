from __future__ import annotations
import time
import uuid
import logging
from typing import Dict, Any, Optional
from contextvars import ContextVar
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import json

# Context variables for tracing
trace_id_var: ContextVar[Optional[str]] = ContextVar('trace_id', default=None)
span_id_var: ContextVar[Optional[str]] = ContextVar('span_id', default=None)
user_id_var: ContextVar[Optional[str]] = ContextVar('user_id', default=None)
tenant_id_var: ContextVar[Optional[str]] = ContextVar('tenant_id', default=None)

class StructuredLogger:
    """Structured logger with trace correlation"""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
        self._setup_formatter()
    
    def _setup_formatter(self):
        """Setup JSON formatter for structured logging"""
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        handler.setFormatter(formatter)
        
        # Remove existing handlers to avoid duplicates
        self.logger.handlers.clear()
        self.logger.addHandler(handler)
        self.logger.setLevel(logging.INFO)
    
    def _get_context(self) -> Dict[str, Any]:
        """Get current context for logging"""
        context = {}
        
        trace_id = trace_id_var.get()
        if trace_id:
            context['trace_id'] = trace_id
        
        span_id = span_id_var.get()
        if span_id:
            context['span_id'] = span_id
        
        user_id = user_id_var.get()
        if user_id:
            context['user_id'] = user_id
        
        tenant_id = tenant_id_var.get()
        if tenant_id:
            context['tenant_id'] = tenant_id
        
        return context
    
    def _log(self, level: str, message: str, extra: Optional[Dict[str, Any]] = None):
        """Log with structured data"""
        context = self._get_context()
        
        if extra:
            context.update(extra)
        
        log_data = {
            'message': message,
            'level': level,
            **context
        }
        
        getattr(self.logger, level.lower())(json.dumps(log_data))
    
    def info(self, message: str, extra: Optional[Dict[str, Any]] = None):
        self._log('INFO', message, extra)
    
    def warning(self, message: str, extra: Optional[Dict[str, Any]] = None):
        self._log('WARNING', message, extra)
    
    def error(self, message: str, extra: Optional[Dict[str, Any]] = None):
        self._log('ERROR', message, extra)
    
    def debug(self, message: str, extra: Optional[Dict[str, Any]] = None):
        self._log('DEBUG', message, extra)

class TracingMiddleware(BaseHTTPMiddleware):
    """Middleware for request tracing and logging"""
    
    def __init__(self, app):
        super().__init__(app)
        self.logger = StructuredLogger(__name__)
    
    async def dispatch(self, request: Request, call_next):
        # Generate trace ID for this request
        trace_id = str(uuid.uuid4())
        span_id = str(uuid.uuid4())
        
        # Set context variables
        trace_id_var.set(trace_id)
        span_id_var.set(span_id)
        
        # Extract user and tenant info from request
        user_id = None
        tenant_id = None
        
        # Get tenant from header (simpler approach)
        tenant_id = request.headers.get("X-Tenant-Id")
        if tenant_id:
            tenant_id_var.set(tenant_id)
        
        # Log request start
        start_time = time.time()
        self.logger.info(
            "Request started",
            {
                "method": request.method,
                "path": request.url.path,
                "query_params": str(request.query_params),
                "user_agent": request.headers.get("User-Agent"),
                "remote_addr": request.client.host if request.client else None
            }
        )
        
        # Process request
        try:
            response = await call_next(request)
            
            # Log request completion
            duration = time.time() - start_time
            self.logger.info(
                "Request completed",
                {
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration * 1000,
                    "response_size": response.headers.get("content-length", 0)
                }
            )
            
            # Add trace headers to response
            response.headers["X-Trace-ID"] = trace_id
            response.headers["X-Span-ID"] = span_id
            
            return response
            
        except Exception as e:
            # Log request error
            duration = time.time() - start_time
            self.logger.error(
                "Request failed",
                {
                    "method": request.method,
                    "path": request.url.path,
                    "error": str(e),
                    "error_type": type(e).__name__,
                    "duration_ms": duration * 1000
                }
            )
            raise
        
        finally:
            # Clear context variables
            trace_id_var.set(None)
            span_id_var.set(None)
            user_id_var.set(None)
            tenant_id_var.set(None)

class MetricsCollector:
    """Simple metrics collector"""
    
    def __init__(self):
        self.counters: Dict[str, int] = {}
        self.histograms: Dict[str, list] = {}
        self.logger = StructuredLogger(__name__)
    
    def increment_counter(self, name: str, labels: Optional[Dict[str, str]] = None):
        """Increment a counter metric"""
        key = self._make_key(name, labels)
        self.counters[key] = self.counters.get(key, 0) + 1
        
        self.logger.info(
            "Counter incremented",
            {
                "metric_name": name,
                "labels": labels or {},
                "value": self.counters[key]
            }
        )
    
    def record_histogram(self, name: str, value: float, labels: Optional[Dict[str, str]] = None):
        """Record a histogram value"""
        key = self._make_key(name, labels)
        if key not in self.histograms:
            self.histograms[key] = []
        
        self.histograms[key].append(value)
        
        self.logger.info(
            "Histogram recorded",
            {
                "metric_name": name,
                "labels": labels or {},
                "value": value,
                "count": len(self.histograms[key])
            }
        )
    
    def _make_key(self, name: str, labels: Optional[Dict[str, str]]) -> str:
        """Create a key for metric storage"""
        if not labels:
            return name
        
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current metrics"""
        return {
            "counters": self.counters.copy(),
            "histograms": {
                key: {
                    "count": len(values),
                    "sum": sum(values),
                    "min": min(values),
                    "max": max(values),
                    "avg": sum(values) / len(values) if values else 0
                }
                for key, values in self.histograms.items()
            }
        }

# Global metrics collector
metrics = MetricsCollector()

def get_logger(name: str) -> StructuredLogger:
    """Get structured logger instance"""
    return StructuredLogger(name)

def mask_pii(data: Dict[str, Any]) -> Dict[str, Any]:
    """Mask personally identifiable information"""
    masked_data = data.copy()
    
    pii_fields = ['email', 'password', 'token', 'secret', 'key']
    
    for field in pii_fields:
        if field in masked_data:
            masked_data[field] = "***"
    
    return masked_data
