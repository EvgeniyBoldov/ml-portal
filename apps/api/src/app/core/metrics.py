from __future__ import annotations
import time
from typing import Callable
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from prometheus_client import Counter, Summary, Gauge, generate_latest, CONTENT_TYPE_LATEST

REQUESTS = Counter(
    "http_requests_total", "Total HTTP requests", ["method", "path", "status"]
)
REQ_LATENCY = Summary(
    "http_request_duration_seconds", "HTTP request latency (seconds)", ["method", "path"]
)
INPROGRESS = Gauge(
    "http_requests_in_progress", "In-progress HTTP requests"
)

class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable):
        start = time.monotonic()
        INPROGRESS.inc()
        try:
            response: Response = await call_next(request)
            status = getattr(response, "status_code", 500)
            REQUESTS.labels(request.method, request.url.path, str(status)).inc()
            REQ_LATENCY.labels(request.method, request.url.path).observe(time.monotonic() - start)
            return response
        finally:
            INPROGRESS.dec()

def mount_metrics_endpoint(app: FastAPI, path: str = "/metrics") -> None:
    @app.get(path)
    def _metrics():
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
