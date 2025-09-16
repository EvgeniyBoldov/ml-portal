import logging
import sys
from typing import Any, Dict, Optional
from datetime import datetime
import json
import traceback

class JSONFormatter(logging.Formatter):
    """Custom JSON formatter for structured logging"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        
        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info)
            }
        
        # Add extra fields
        if hasattr(record, 'extra'):
            log_entry.update(record.extra)
        
        return json.dumps(log_entry, ensure_ascii=False)

def setup_logging(level: str = "INFO") -> None:
    """Setup structured logging configuration"""
    
    # Create logger
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, level.upper()))
    
    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # Create console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, level.upper()))
    
    # Set formatter
    formatter = JSONFormatter()
    console_handler.setFormatter(formatter)
    
    # Add handler to logger
    logger.addHandler(console_handler)
    
    # Set specific loggers
    logging.getLogger("uvicorn").setLevel(logging.INFO)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("fastapi").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

def get_logger(name: str) -> logging.Logger:
    """Get logger instance"""
    return logging.getLogger(name)

class LoggerMixin:
    """Mixin class for adding logging to any class"""
    
    @property
    def logger(self) -> logging.Logger:
        return get_logger(f"{self.__class__.__module__}.{self.__class__.__name__}")

def log_api_call(
    logger: logging.Logger,
    method: str,
    endpoint: str,
    user_id: Optional[str] = None,
    status_code: Optional[int] = None,
    duration_ms: Optional[float] = None,
    error: Optional[str] = None
) -> None:
    """Log API call with structured data"""
    extra = {
        "api_call": {
            "method": method,
            "endpoint": endpoint,
            "user_id": user_id,
            "status_code": status_code,
            "duration_ms": duration_ms,
            "error": error
        }
    }
    
    if error:
        logger.error(f"API call failed: {method} {endpoint}", extra=extra)
    else:
        logger.info(f"API call: {method} {endpoint}", extra=extra)

def log_database_operation(
    logger: logging.Logger,
    operation: str,
    table: str,
    record_id: Optional[str] = None,
    duration_ms: Optional[float] = None,
    error: Optional[str] = None
) -> None:
    """Log database operation with structured data"""
    extra = {
        "db_operation": {
            "operation": operation,
            "table": table,
            "record_id": record_id,
            "duration_ms": duration_ms,
            "error": error
        }
    }
    
    if error:
        logger.error(f"Database operation failed: {operation} on {table}", extra=extra)
    else:
        logger.info(f"Database operation: {operation} on {table}", extra=extra)

def log_external_service(
    logger: logging.Logger,
    service: str,
    operation: str,
    duration_ms: Optional[float] = None,
    error: Optional[str] = None,
    **kwargs
) -> None:
    """Log external service call with structured data"""
    extra = {
        "external_service": {
            "service": service,
            "operation": operation,
            "duration_ms": duration_ms,
            "error": error,
            **kwargs
        }
    }
    
    if error:
        logger.error(f"External service call failed: {service}.{operation}", extra=extra)
    else:
        logger.info(f"External service call: {service}.{operation}", extra=extra)