from __future__ import annotations
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from app.core.metrics import prometheus_endpoint
from app.core.logging import setup_logging, get_logger
from app.core.errors import install_exception_handlers
from app.core.config import settings
from app.core.db import engine, db_manager
from app.core.redis import get_redis, redis_manager
from app.core.qdrant import get_qdrant
from app.core.s3 import get_minio, s3_manager
from app.core.idempotency import IdempotencyMiddleware
from app.core.request_id import RequestIDMiddleware
from app.core.security_headers import SecurityHeadersMiddleware
from app.api.routers.auth import router as auth_router
from app.api.routers.chats import router as chats_router
from app.api.routers.rag import router as rag_router
# from app.api.routers.rag_search import router as rag_search_router  # TODO: Fix missing multi_index_search
from app.api.routers.analyze import router as analyze_router
from app.api.routers.admin import router as admin_router
from app.api.routers.password_reset import router as password_reset_router
from app.api.routers.setup import router as setup_router

setup_logging()
logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    logger.info("Starting ML Portal application...")
    
    # Инициализация подключений
    try:
        # Проверяем подключение к базе данных
        if hasattr(db_manager, 'async_health_check'):
            await db_manager.async_health_check()
        logger.info("Database connection established")
        
        # Проверяем подключение к Redis
        if hasattr(redis_manager, 'ping_async'):
            await redis_manager.ping_async()
        logger.info("Redis connection established")
        
        # Проверяем подключение к S3
        if hasattr(s3_manager, 'health_check'):
            s3_manager.health_check()
        logger.info("S3 connection established")
        
        # Проверяем подключение к Qdrant
        try:
            qdrant = get_qdrant()
            qdrant.get_collections()
            logger.info("Qdrant connection established")
        except Exception as e:
            logger.warning(f"Qdrant connection failed: {e}")
        
        logger.info("All connections established successfully")
        
    except Exception as e:
        logger.error(f"Failed to establish connections: {e}")
        # Не прерываем запуск приложения, только логируем ошибку
    
    yield
    
    # Очистка при завершении
    logger.info("Shutting down ML Portal application...")
    try:
        # Close connections gracefully
        if hasattr(db_manager, 'close'):
            db_manager.close()
        if hasattr(redis_manager, 'close'):
            redis_manager.close()
        logger.info("Connections closed successfully")
    except Exception as e:
        logger.error(f"Error during shutdown: {e}")

# Создание FastAPI приложения
app = FastAPI(
    title="ML Portal API",
    description="ML Portal with consolidated architecture",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(RequestIDMiddleware)
app.add_middleware(SecurityHeadersMiddleware, environment=os.getenv("ENVIRONMENT", "development"))
app.add_middleware(IdempotencyMiddleware)

if os.getenv("CORS_ENABLED", "1") not in {"0", "false", "False"}:
    origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",")]
    # В DEV разрешаем все origins, в PROD - только явно указанные
    is_dev = os.getenv("ENVIRONMENT", "development") == "development"
    
    if is_dev or origins == ["*"]:
        # DEV режим - разрешаем все origins, но без credentials
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    else:
        # PROD режим - только указанные origins с credentials
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        )

install_exception_handlers(app)

@app.get("/healthz")
@app.get("/health")  # Алиас для совместимости с тестами
async def health_check(deep: bool = False):
    """Проверка здоровья приложения"""
    try:
        if deep or settings.HEALTH_DEEP:
            # Глубокая проверка всех сервисов
            health_status = {
                "status": "healthy",
                "services": {}
            }
            
            # Проверка базы данных
            try:
                if hasattr(db_manager, 'async_health_check'):
                    await db_manager.async_health_check()
                else:
                    with engine.connect() as conn:
                        conn.execute(text("SELECT 1"))
                health_status["services"]["database"] = "healthy"
            except Exception as e:
                health_status["services"]["database"] = f"unhealthy: {e}"
                health_status["status"] = "degraded"
            
            # Проверка Redis
            try:
                if hasattr(redis_manager, 'ping_async'):
                    await redis_manager.ping_async()
                else:
                    await get_redis().ping()
                health_status["services"]["redis"] = "healthy"
            except Exception as e:
                health_status["services"]["redis"] = f"unhealthy: {e}"
                health_status["status"] = "degraded"
            
            # Проверка S3
            try:
                if hasattr(s3_manager, 'health_check'):
                    s3_manager.health_check()
                else:
                    get_minio().list_buckets()
                health_status["services"]["s3"] = "healthy"
            except Exception as e:
                health_status["services"]["s3"] = f"unhealthy: {e}"
                health_status["status"] = "degraded"
            
            # Проверка Qdrant
            try:
                qdrant = get_qdrant()
                qdrant.get_collections()
                health_status["services"]["qdrant"] = "healthy"
            except Exception as e:
                health_status["services"]["qdrant"] = f"unhealthy: {e}"
                health_status["status"] = "degraded"
            
            return health_status
        else:
            return {"status": "healthy", "message": "Service is running"}
            
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "error": str(e)}
        )

@app.get("/metrics")
def metrics():
    """Prometheus метрики"""
    return prometheus_endpoint()

@app.get("/api/v2/status")
async def system_status():
    """Расширенный статус системы"""
    try:
        # Получаем статистику из Redis если доступен
        redis_client = get_redis()
        try:
            await redis_client.ping()
            system_stats = await redis_client.get("system_statistics")
        except Exception:
            system_stats = None
        
        return {
            "status": "operational",
            "version": "2.0.0",
            "statistics": system_stats,
            "timestamp": "2024-01-01T00:00:00Z"  # TODO: использовать реальное время
        }
    except Exception as e:
        logger.error(f"Failed to get system status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/rag/metrics")
def rag_metrics():
    from app.api.deps import db_session
    from sqlalchemy import func
    from app.models.rag import RAGDocument, RAGChunk
    
    session = next(db_session())
    try:
        # Подсчитываем документы по статусам
        status_counts = session.query(
            RAGDocument.status,
            func.count(RAGDocument.id)
        ).group_by(RAGDocument.status).all()
        
        # Общее количество документов
        total_documents = session.query(func.count(RAGDocument.id)).scalar()
        
        # Количество чанков
        total_chunks = session.query(func.count(RAGChunk.id)).scalar()
        
        # Количество документов в обработке
        processing_documents = session.query(func.count(RAGDocument.id)).filter(
            RAGDocument.status.in_(['uploaded', 'normalizing', 'chunking', 'embedding', 'indexing'])
        ).scalar()
        
        # Размер хранилища (приблизительно)
        storage_size = session.query(func.sum(RAGDocument.size_bytes)).scalar() or 0
        
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
# app.include_router(rag_search_router, prefix="/api")  # TODO: Fix missing multi_index_search
app.include_router(analyze_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.include_router(password_reset_router, prefix="/api")
app.include_router(setup_router, prefix="/api")
