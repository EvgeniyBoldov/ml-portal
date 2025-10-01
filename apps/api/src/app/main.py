from __future__ import annotations
from fastapi import FastAPI
from app.api.v1.router import router as v1_router
from app.core.middleware import RequestIDMiddleware
from app.core.middleware_rate_limit_headers import RateLimitHeadersMiddleware
from app.core.exception_handlers import setup_exception_handlers
from app.core.metrics import MetricsMiddleware, mount_metrics_endpoint
from app.core.di import cleanup_clients
from app.core.config import settings

def create_app() -> FastAPI:
    app = FastAPI(title="ml-portal api")

    # Middlewares
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(RateLimitHeadersMiddleware)
    app.add_middleware(MetricsMiddleware)

    # Routers
    app.include_router(v1_router, prefix="")

    # Exception handlers -> ProblemDetails JSON
    setup_exception_handlers(app)

    # /metrics endpoint (Prometheus)
    mount_metrics_endpoint(app, path="/metrics")

    # Shutdown cleanup
    @app.on_event("shutdown")
    async def _shutdown():
        await cleanup_clients()

    # Optional: debug-only routes hook (only if such function exists)
    if getattr(settings, "DEBUG", False):
        try:
            from app.core.debug_routes import setup_debug_routes  # type: ignore
            setup_debug_routes(app)  # only if implemented in your codebase
        except Exception:
            pass

    return app

app = create_app()
