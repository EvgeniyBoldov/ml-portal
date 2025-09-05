from __future__ import annotations
import json, logging, sys, uuid, contextvars
from typing import Any, Mapping, Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

request_id_ctx = contextvars.ContextVar("request_id", default=None)

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
        }
        rid = request_id_ctx.get()
        if rid:
            payload["request_id"] = rid
        # Extra
        for k, v in record.__dict__.items():
            if k not in ("args", "asctime", "created", "exc_info", "exc_text", "filename",
                         "funcName", "levelname", "levelno", "lineno", "module", "msecs",
                         "message", "msg", "name", "pathname", "process", "processName",
                         "relativeCreated", "stack_info", "thread", "threadName"):
                payload[k] = v
        return json.dumps(payload, ensure_ascii=False)

def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

class RequestIdMiddleware(BaseHTTPMiddleware):
    header_name = "X-Request-ID"
    async def dispatch(self, request: Request, call_next):
        rid = request.headers.get(self.header_name) or str(uuid.uuid4())
        token = request_id_ctx.set(rid)
        try:
            response: Response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        response.headers[self.header_name] = rid
        return response
