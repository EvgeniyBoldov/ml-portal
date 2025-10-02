from __future__ import annotations
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.router import router as v1_router
from app.core.middleware import RequestContextMiddleware
from app.core.exception_handlers import setup_exception_handlers
from app.core.di import cleanup_clients
from app.core.config import get_settings

def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="ml-portal api")

    # CORS
    allow_origins = [o.strip() for o in s.CORS_ALLOW_ORIGINS.split(",") if o.strip()]
    app.add_middleware(CORSMiddleware, allow_origins=allow_origins, allow_credentials=False, allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Request-ID","X-API-Version","X-RateLimit-Limit","X-RateLimit-Remaining","X-RateLimit-Reset","Retry-After"])

    # Middlewares
    app.add_middleware(RequestContextMiddleware)

    # Routers with /api/v1 prefix
    app.include_router(v1_router, prefix="/api/v1")

    # Exception handlers -> ProblemDetails JSON
    setup_exception_handlers(app)

    # Startup guard: fail if staging/prod with DEBUG=True
    if s.ENV in {"staging","prod"} and s.DEBUG:
        raise RuntimeError("DEBUG must be False in staging/prod")

    # Shutdown cleanup
    @app.on_event("shutdown")
    async def _shutdown():
        await cleanup_clients()

    return app

app = create_app()
