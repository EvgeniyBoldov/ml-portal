from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.router import api_v1
from app.core.db import lifespan
from app.core.exceptions import install_exception_handlers
from app.core.middleware import (
    GlobalRateLimitMiddleware,
    RequestContextMiddleware,
    StartupReadinessMiddleware,
    TenantMiddleware,
    TimeoutMiddleware,
)

app = FastAPI(title="ML-Portal API", lifespan=lifespan)

install_exception_handlers(app)

from app.core.config import get_settings
settings = get_settings()

if not getattr(settings, "CORS_ALLOW_ORIGINS", None) or settings.CORS_ALLOW_ORIGINS.strip() == "*":
    allowed_origins = [
        "http://localhost",
        "http://localhost:5173",
        "http://localhost:8080",
        "http://127.0.0.1",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8080",
    ]
else:
    allowed_origins = [o.strip() for o in settings.CORS_ALLOW_ORIGINS.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Idempotency-Key", "X-Tenant-Id", "X-Request-ID", "Last-Event-ID"],
    expose_headers=["X-Total-Count", "X-Page", "X-Page-Size"],
)
app.add_middleware(TimeoutMiddleware)
app.add_middleware(TenantMiddleware)
app.add_middleware(GlobalRateLimitMiddleware)
app.add_middleware(StartupReadinessMiddleware)
app.add_middleware(RequestContextMiddleware)


@app.get("/version")
async def version():
    return {"version": "0.0.0", "build_time": "", "git_commit": ""}

@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint"""
    from app.core.prometheus_metrics import get_metrics_text, record_db_pool_stats
    from app.core.db import get_pool_stats
    from fastapi.responses import Response
    record_db_pool_stats(get_pool_stats())
    return Response(
        content=get_metrics_text(),
        media_type="text/plain; version=0.0.4"
    )

app.include_router(api_v1, prefix="/api/v1")
