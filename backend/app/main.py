from __future__ import annotations
from fastapi import FastAPI
from sqlalchemy import text
from app.core.metrics import prometheus_endpoint
from app.core.logging import RequestIdMiddleware, setup_logging
from app.core.errors import install_exception_handlers
from app.core.config import settings
from app.core.db import engine
from app.core.redis import get_redis
from app.core.qdrant import get_qdrant
from app.core.s3 import get_minio
from app.api.routers.auth import router as auth_router
from app.api.routers.chats import router as chats_router
from app.api.routers.rag import router as rag_router

setup_logging()

app = FastAPI(title="API")

# Middlewares & handlers
app.add_middleware(RequestIdMiddleware)
install_exception_handlers(app)

@app.get("/healthz")
async def healthz(deep: int | None = None):
    if settings.HEALTH_DEEP or deep == 1:
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            await get_redis().ping()
            get_qdrant().get_collections()
            get_minio().list_buckets()
        except Exception as e:
            return {"ok": False, "error": str(e)}
    return {"ok": True}

@app.get("/metrics")
def metrics():
    return prometheus_endpoint()

# Routers
app.include_router(auth_router, prefix="/api")
app.include_router(chats_router, prefix="/api")
app.include_router(rag_router, prefix="/api")
