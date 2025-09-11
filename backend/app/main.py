from __future__ import annotations
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.core.metrics import prometheus_endpoint
from app.core.logging import setup_logging
from app.core.errors import install_exception_handlers
from app.core.config import settings
from app.core.db import engine
from app.core.redis import get_redis
from app.core.qdrant import get_qdrant
from app.core.s3 import get_minio
from app.core.idempotency import IdempotencyMiddleware
from app.api.routers.auth import router as auth_router
from app.api.routers.chats import router as chats_router
from app.api.routers.rag import router as rag_router
from app.api.routers.analyze import router as analyze_router

setup_logging()

app = FastAPI(title="API")

app.add_middleware(IdempotencyMiddleware)

if os.getenv("CORS_ENABLED", "1") not in {"0", "false", "False"}:
    origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",")]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins if origins != ["*"] else ["*"],
        allow_credentials=True,
        allow_methods=[m.strip() for m in os.getenv("CORS_METHODS", "*").split(",")] if os.getenv("CORS_METHODS") else ["*"],
        allow_headers=[h.strip() for h in os.getenv("CORS_HEADERS", "*").split(",")] if os.getenv("CORS_HEADERS") else ["*"],
        expose_headers=[h.strip() for h in os.getenv("CORS_EXPOSE_HEADERS", "").split(",")] if os.getenv("CORS_EXPOSE_HEADERS") else [],
        max_age=int(os.getenv("CORS_MAX_AGE", "600")),
    )

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

@app.get("/api/rag/metrics")
def rag_metrics():
    from app.api.deps import db_session
    from sqlalchemy import func
    from app.models.rag import RagDocuments, RagChunks
    
    session = next(db_session())
    try:
        # Подсчитываем документы по статусам
        status_counts = session.query(
            RagDocuments.status,
            func.count(RagDocuments.id)
        ).group_by(RagDocuments.status).all()
        
        # Общее количество документов
        total_documents = session.query(func.count(RagDocuments.id)).scalar()
        
        # Количество чанков
        total_chunks = session.query(func.count(RagChunks.id)).scalar()
        
        # Количество документов в обработке
        processing_documents = session.query(func.count(RagDocuments.id)).filter(
            RagDocuments.status.in_(['uploaded', 'normalizing', 'chunking', 'embedding', 'indexing'])
        ).scalar()
        
        # Размер хранилища (приблизительно)
        storage_size = session.query(func.sum(RagDocuments.size_bytes)).scalar() or 0
        
        return {
            "total_documents": total_documents,
            "total_chunks": total_chunks,
            "processing_documents": processing_documents,
            "storage_size_bytes": storage_size,
            "storage_size_mb": round(storage_size / (1024 * 1024), 2),
            "status_breakdown": {status: count for status, count in status_counts},
            "ready_documents": next((count for status, count in status_counts if status == 'ready'), 0),
            "error_documents": next((count for status, count in status_counts if status == 'error'), 0)
        }
    finally:
        session.close()

app.include_router(auth_router, prefix="/api")
app.include_router(chats_router, prefix="/api")
app.include_router(rag_router, prefix="/api")
app.include_router(analyze_router, prefix="/api")
