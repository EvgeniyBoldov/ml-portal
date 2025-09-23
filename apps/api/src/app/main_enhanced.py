"""
Улучшенное главное приложение ML Portal
Интегрирует все новые компоненты и сервисы
"""
from __future__ import annotations
import os
import logging
from contextlib import asynccontextmanager
from typing import Dict, Any

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

# Импорты конфигурации и утилит
from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.core.metrics import prometheus_endpoint
from app.core.errors import install_exception_handlers
from app.core.db import db_manager
from app.core.redis import redis_manager
from app.core.s3 import s3_manager
from app.core.qdrant import get_qdrant

# Middleware
from app.core.idempotency import IdempotencyMiddleware
from app.core.request_id import RequestIDMiddleware
from app.core.security_headers import SecurityHeadersMiddleware

# API роутеры (legacy)
from app.api.routers.auth import router as auth_router
from app.api.routers.chats import router as chats_router
from app.api.routers.rag import router as rag_router
from app.api.routers.analyze import router as analyze_router
from app.api.routers.admin import router as admin_router
from app.api.routers.password_reset import router as password_reset_router
from app.api.routers.setup import router as setup_router

# Новые улучшенные компоненты
from app.api.controllers.users import UsersController
from app.api.controllers.chats import ChatsController, ChatMessagesController
from app.api.controllers.rag import RAGDocumentsController, RAGChunksController
from app.services.users_service_enhanced import UsersService
from app.services.chats_service_enhanced import ChatsService, ChatMessagesService
from app.services.rag_service_enhanced import RAGDocumentsService, RAGChunksService
from app.api.schemas.users import UserCreateRequest
from app.api.schemas.chats import ChatCreateRequest
from app.api.schemas.rag import RAGDocumentCreateRequest
from app.tasks.task_manager import task_manager

# Настройка логирования
setup_logging()
logger = get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Управление жизненным циклом приложения"""
    logger.info("Starting ML Portal application...")
    
    # Инициализация подключений
    try:
        # Проверяем подключение к базе данных
        await db_manager.async_health_check()
        logger.info("Database connection established")
        
        # Проверяем подключение к Redis
        await redis_manager.ping_async()
        logger.info("Redis connection established")
        
        # Проверяем подключение к S3
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
        raise
    
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
    description="Enhanced ML Portal with improved architecture",
    version="2.0.0",
    lifespan=lifespan
)

# Middleware
app.add_middleware(RequestIDMiddleware)
app.add_middleware(SecurityHeadersMiddleware, environment=os.getenv("ENVIRONMENT", "development"))
app.add_middleware(IdempotencyMiddleware)

# CORS настройки
if os.getenv("CORS_ENABLED", "1") not in {"0", "false", "False"}:
    origins = [o.strip() for o in os.getenv("CORS_ORIGINS", "*").split(",")]
    is_dev = os.getenv("ENVIRONMENT", "development") == "development"
    
    if is_dev or origins == ["*"]:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=False,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    else:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        )

# Установка обработчиков исключений
install_exception_handlers(app)

# Health check endpoints
@app.get("/healthz")
@app.get("/health")
async def health_check(deep: bool = False):
    """Проверка здоровья приложения"""
    try:
        if deep:
            # Глубокая проверка всех сервисов
            health_status = {
                "status": "healthy",
                "services": {}
            }
            
            # Проверка базы данных
            try:
                await db_manager.async_health_check()
                health_status["services"]["database"] = "healthy"
            except Exception as e:
                health_status["services"]["database"] = f"unhealthy: {e}"
                health_status["status"] = "degraded"
            
            # Проверка Redis
            try:
                await redis_manager.ping_async()
                health_status["services"]["redis"] = "healthy"
            except Exception as e:
                health_status["services"]["redis"] = f"unhealthy: {e}"
                health_status["status"] = "degraded"
            
            # Проверка S3
            try:
                s3_manager.health_check()
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
        # Получаем статистику очередей
        queue_stats = await task_manager.get_queue_stats()
        
        # Получаем статистику воркеров
        worker_stats = await task_manager.get_worker_stats()
        
        # Получаем статистику из Redis
        redis_client = redis_manager.get_async_redis()
        system_stats = await redis_client.get("system_statistics")
        
        return {
            "status": "operational",
            "version": "2.0.0",
            "queues": queue_stats,
            "workers": worker_stats,
            "statistics": system_stats,
            "timestamp": "2024-01-01T00:00:00Z"  # TODO: использовать реальное время
        }
    except Exception as e:
        logger.error(f"Failed to get system status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# API v2 endpoints с новыми контроллерами
@app.post("/api/v2/users")
async def create_user_v2(request: UserCreateRequest, current_user: dict = None):
    """Создание пользователя через новый API"""
    try:
        async with await db_manager.get_async_session() as session:
            users_service = UsersService(session)
            controller = UsersController(users_service)
            return await controller.create_user(request.dict(), current_user or {})
    except Exception as e:
        logger.error(f"Failed to create user: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v2/users/{user_id}")
async def get_user_v2(user_id: str, current_user: dict = None):
    """Получение пользователя через новый API"""
    try:
        async with await db_manager.get_async_session() as session:
            users_service = UsersService(session)
            controller = UsersController(users_service)
            return await controller.get_user(user_id, current_user or {})
    except Exception as e:
        logger.error(f"Failed to get user: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v2/chats")
async def create_chat_v2(request: ChatCreateRequest, current_user: dict = None):
    """Создание чата через новый API"""
    try:
        async with await db_manager.get_async_session() as session:
            chats_service = ChatsService(session)
            controller = ChatsController(chats_service)
            return await controller.create_chat(request.dict(), current_user or {})
    except Exception as e:
        logger.error(f"Failed to create chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v2/chats/{chat_id}")
async def get_chat_v2(chat_id: str, current_user: dict = None):
    """Получение чата через новый API"""
    try:
        async with await db_manager.get_async_session() as session:
            chats_service = ChatsService(session)
            controller = ChatsController(chats_service)
            return await controller.get_chat(chat_id, current_user or {})
    except Exception as e:
        logger.error(f"Failed to get chat: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v2/rag/documents")
async def create_rag_document_v2(request: RAGDocumentCreateRequest, current_user: dict = None):
    """Создание RAG документа через новый API"""
    try:
        async with await db_manager.get_async_session() as session:
            rag_service = RAGDocumentsService(session)
            controller = RAGDocumentsController(rag_service)
            return await controller.create_document(request.dict(), current_user or {})
    except Exception as e:
        logger.error(f"Failed to create RAG document: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v2/rag/documents/{document_id}")
async def get_rag_document_v2(document_id: str, current_user: dict = None):
    """Получение RAG документа через новый API"""
    try:
        async with await db_manager.get_async_session() as session:
            rag_service = RAGDocumentsService(session)
            controller = RAGDocumentsController(rag_service)
            return await controller.get_document(document_id, current_user or {})
    except Exception as e:
        logger.error(f"Failed to get RAG document: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Task management endpoints
@app.post("/api/v2/tasks/process-document")
async def process_document_task(document_id: str, source_key: str = None, priority: str = "normal"):
    """Запуск задачи обработки документа"""
    try:
        result = await task_manager.process_document_async(document_id, source_key, priority)
        return result
    except Exception as e:
        logger.error(f"Failed to start document processing task: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v2/tasks/{task_id}")
async def get_task_status(task_id: str):
    """Получение статуса задачи"""
    try:
        result = await task_manager.get_task_status(task_id)
        return result
    except Exception as e:
        logger.error(f"Failed to get task status: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/v2/tasks/{task_id}/cancel")
async def cancel_task(task_id: str):
    """Отмена задачи"""
    try:
        result = await task_manager.cancel_task(task_id)
        return {"success": result}
    except Exception as e:
        logger.error(f"Failed to cancel task: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/v2/tasks/queues/stats")
async def get_queue_stats():
    """Статистика очередей"""
    try:
        result = await task_manager.get_queue_stats()
        return result
    except Exception as e:
        logger.error(f"Failed to get queue stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# Legacy API endpoints (для обратной совместимости)
app.include_router(auth_router, prefix="/api")
app.include_router(chats_router, prefix="/api")
app.include_router(rag_router, prefix="/api")
app.include_router(analyze_router, prefix="/api")
app.include_router(admin_router)
app.include_router(password_reset_router)
app.include_router(setup_router)

# RAG метрики (legacy)
@app.get("/api/rag/metrics")
def rag_metrics():
    """RAG метрики (legacy endpoint)"""
    try:
        # Используем синхронную версию для совместимости
        from app.core.db import SessionLocal
        from sqlalchemy import func
        from app.models.rag import RagDocuments, RagChunks
        
        session = SessionLocal()
        try:
            status_counts = session.query(
                RagDocuments.status,
                func.count(RagDocuments.id)
            ).group_by(RagDocuments.status).all()
            
            total_documents = session.query(func.count(RagDocuments.id)).scalar()
            total_chunks = session.query(func.count(RagChunks.id)).scalar()
            processing_documents = session.query(func.count(RagDocuments.id)).filter(
                RagDocuments.status.in_(['uploaded', 'normalizing', 'chunking', 'embedding', 'indexing'])
            ).scalar()
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
    except Exception as e:
        logger.error(f"Failed to get RAG metrics: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main_enhanced:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
