"""
Периодические задачи для ML Portal
Задачи, выполняемые по расписанию
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from celery import shared_task
from celery.schedules import crontab

from app.celery_app import app as celery_app
from app.core.config import get_settings
from app.core.db import get_async_session
from app.core.redis import redis_manager
from app.services.rag_service import RAGDocumentsService, RAGChunksService
# from app.tasks.bg_tasks_enhanced import cleanup_old_documents
from app.workers.tasks_ingest import task_manager
from app.workers import log, task_metrics

logger = logging.getLogger(__name__)

# Настройка расписания задач
celery_app.conf.beat_schedule = {
    # Очистка старых документов - каждый день в 2:00
    'cleanup-old-documents': {
        'task': 'periodic_tasks.cleanup_old_documents_daily',
        'schedule': crontab(hour=2, minute=0),
    },
    
    # Проверка здоровья системы - каждые 5 минут
    'health-check': {
        'task': 'periodic_tasks.system_health_check',
        'schedule': crontab(minute='*/5'),
    },
    
    # Обновление статистики - каждый час
    'update-statistics': {
        'task': 'periodic_tasks.update_system_statistics',
        'schedule': crontab(minute=0),
    },
    
    # Очистка временных файлов - каждые 6 часов
    'cleanup-temp-files': {
        'task': 'periodic_tasks.cleanup_temp_files',
        'schedule': crontab(minute=0, hour='*/6'),
    },
    
    # Переиндексация проблемных документов - каждый день в 3:00
    'reindex-failed-documents': {
        'task': 'periodic_tasks.reindex_failed_documents',
        'schedule': crontab(hour=3, minute=0),
    },
    
    # Мониторинг очередей - каждые 10 минут
    'monitor-queues': {
        'task': 'periodic_tasks.monitor_queue_health',
        'schedule': crontab(minute='*/10'),
    },
}

@shared_task(name="periodic_tasks.cleanup_old_documents_daily", bind=True)
def cleanup_old_documents_daily(self) -> Dict[str, Any]:
    """
    Ежедневная очистка старых документов
    
    Returns:
        Результат очистки
    """
    with task_metrics("cleanup_old_documents_daily", "maintenance"):
        try:
            logger.info("Starting daily cleanup of old documents")
            
            # Получаем настройки из конфигурации
            s = get_settings()
            days_old = getattr(s, 'CLEANUP_DAYS_OLD', 30)
            
            # Запускаем очистку
            result = cleanup_old_documents.delay(days_old)
            
            logger.info(f"Daily cleanup task started: {result.id}")
            return {
                "success": True,
                "task_id": result.id,
                "days_old": days_old,
                "scheduled_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to start daily cleanup: {e}")
            return {"success": False, "error": str(e)}

@shared_task(name="periodic_tasks.system_health_check", bind=True)
def system_health_check(self) -> Dict[str, Any]:
    """
    Проверка здоровья системы
    
    Returns:
        Статус здоровья системы
    """
    with task_metrics("system_health_check", "monitoring"):
        try:
            logger.info("Starting system health check")
            
            health_status = {
                "timestamp": datetime.utcnow().isoformat(),
                "overall_status": "healthy",
                "components": {}
            }
            
            # Проверяем базу данных
            db_status = asyncio.run(check_database_health())
            health_status["components"]["database"] = db_status
            
            # Проверяем Redis
            redis_status = asyncio.run(check_redis_health())
            health_status["components"]["redis"] = redis_status
            
            # Проверяем S3
            s3_status = asyncio.run(check_s3_health())
            health_status["components"]["s3"] = s3_status
            
            # Проверяем очереди задач
            queue_status = asyncio.run(check_queue_health())
            health_status["components"]["queues"] = queue_status
            
            # Определяем общий статус
            all_healthy = all(
                comp.get("status") == "healthy" 
                for comp in health_status["components"].values()
            )
            health_status["overall_status"] = "healthy" if all_healthy else "degraded"
            
            # Сохраняем статус в Redis
            asyncio.run(redis_manager.set_async(
                "system_health", 
                health_status, 
                expire=300  # 5 минут
            ))
            
            logger.info(f"System health check completed: {health_status['overall_status']}")
            return health_status
            
        except Exception as e:
            logger.error(f"System health check failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.utcnow().isoformat()
            }

@shared_task(name="periodic_tasks.update_system_statistics", bind=True)
def update_system_statistics(self) -> Dict[str, Any]:
    """
    Обновление статистики системы
    
    Returns:
        Обновленная статистика
    """
    with task_metrics("update_system_statistics", "monitoring"):
        try:
            logger.info("Updating system statistics")
            
            stats = asyncio.run(gather_system_statistics())
            
            # Сохраняем статистику в Redis
            asyncio.run(redis_manager.set_async(
                "system_statistics",
                stats,
                expire=3600  # 1 час
            ))
            
            logger.info("System statistics updated")
            return {
                "success": True,
                "statistics": stats,
                "updated_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to update system statistics: {e}")
            return {"success": False, "error": str(e)}

@shared_task(name="periodic_tasks.cleanup_temp_files", bind=True)
def cleanup_temp_files(self) -> Dict[str, Any]:
    """
    Очистка временных файлов
    
    Returns:
        Результат очистки
    """
    with task_metrics("cleanup_temp_files", "maintenance"):
        try:
            logger.info("Starting cleanup of temporary files")
            
            # Очищаем временные файлы из Redis
            temp_keys = asyncio.run(redis_manager.keys_async("temp:*"))
            if temp_keys:
                asyncio.run(redis_manager.delete_async(*temp_keys))
            
            # Очищаем устаревшие задачи
            old_tasks = asyncio.run(cleanup_old_task_info())
            
            logger.info(f"Cleanup completed: {len(temp_keys)} temp keys, {old_tasks} old tasks")
            return {
                "success": True,
                "temp_keys_cleaned": len(temp_keys),
                "old_tasks_cleaned": old_tasks,
                "cleaned_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to cleanup temp files: {e}")
            return {"success": False, "error": str(e)}

@shared_task(name="periodic_tasks.reindex_failed_documents", bind=True)
def reindex_failed_documents(self) -> Dict[str, Any]:
    """
    Переиндексация документов с неудачной обработкой
    
    Returns:
        Результат переиндексации
    """
    with task_metrics("reindex_failed_documents", "maintenance"):
        try:
            logger.info("Starting reindex of failed documents")
            
            # Получаем документы со статусом "failed"
            failed_docs = asyncio.run(get_failed_documents())
            
            if not failed_docs:
                logger.info("No failed documents found for reindexing")
                return {
                    "success": True,
                    "reindexed_count": 0,
                    "message": "No failed documents found"
                }
            
            # Запускаем переиндексацию для каждого документа
            reindexed_count = 0
            for doc_id in failed_docs:
                try:
                    # Сбрасываем статус на "pending"
                    asyncio.run(reset_document_status(doc_id, "pending"))
                    
                    # Запускаем обработку
                    task_info = asyncio.run(
                        task_manager.process_document_async(doc_id, priority="low")
                    )
                    
                    reindexed_count += 1
                    logger.info(f"Reindexing started for document {doc_id}: {task_info['task_id']}")
                    
                except Exception as e:
                    logger.error(f"Failed to reindex document {doc_id}: {e}")
                    continue
            
            logger.info(f"Reindex completed: {reindexed_count} documents")
            return {
                "success": True,
                "reindexed_count": reindexed_count,
                "total_failed": len(failed_docs),
                "reindexed_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to reindex documents: {e}")
            return {"success": False, "error": str(e)}

@shared_task(name="periodic_tasks.monitor_queue_health", bind=True)
def monitor_queue_health(self) -> Dict[str, Any]:
    """
    Мониторинг здоровья очередей
    
    Returns:
        Статус очередей
    """
    with task_metrics("monitor_queue_health", "monitoring"):
        try:
            logger.info("Monitoring queue health")
            
            # Получаем статистику очередей
            queue_stats = asyncio.run(task_manager.get_queue_stats())
            
            # Проверяем переполнение очередей
            alerts = []
            for queue_name, stats in queue_stats.get("queues", {}).items():
                total_tasks = stats.get("active", 0) + stats.get("scheduled", 0) + stats.get("reserved", 0)
                
                # Предупреждение при большом количестве задач
                if total_tasks > 100:
                    alerts.append({
                        "queue": queue_name,
                        "level": "warning",
                        "message": f"High task count: {total_tasks}",
                        "count": total_tasks
                    })
                elif total_tasks > 500:
                    alerts.append({
                        "queue": queue_name,
                        "level": "critical",
                        "message": f"Very high task count: {total_tasks}",
                        "count": total_tasks
                    })
            
            # Сохраняем статус очередей
            queue_health = {
                "timestamp": datetime.utcnow().isoformat(),
                "stats": queue_stats,
                "alerts": alerts,
                "status": "healthy" if not alerts else "degraded"
            }
            
            asyncio.run(redis_manager.set_async(
                "queue_health",
                queue_health,
                expire=600  # 10 минут
            ))
            
            logger.info(f"Queue health monitoring completed: {len(alerts)} alerts")
            return queue_health
            
        except Exception as e:
            logger.error(f"Queue health monitoring failed: {e}")
            return {"success": False, "error": str(e)}

# Вспомогательные функции

async def check_database_health() -> Dict[str, Any]:
    """Проверка здоровья базы данных"""
    try:
        async with get_async_session() as session:
            # Простой запрос для проверки соединения
            from sqlalchemy import text
            result = await session.execute(text("SELECT 1"))
            result.scalar()
            
            return {
                "status": "healthy",
                "response_time_ms": 0,  # TODO: измерить реальное время
                "checked_at": datetime.utcnow().isoformat()
            }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "checked_at": datetime.utcnow().isoformat()
        }

async def check_redis_health() -> Dict[str, Any]:
    """Проверка здоровья Redis"""
    try:
        # Простой ping
        asyncio.run(redis_manager.ping_async())
        
        return {
            "status": "healthy",
            "checked_at": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "checked_at": datetime.utcnow().isoformat()
        }

async def check_s3_health() -> Dict[str, Any]:
    """Проверка здоровья S3"""
    try:
        # Проверяем доступность S3
        health = await s3_manager.health_check_async()
        
        return {
            "status": "healthy" if health else "unhealthy",
            "checked_at": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "checked_at": datetime.utcnow().isoformat()
        }

async def check_queue_health() -> Dict[str, Any]:
    """Проверка здоровья очередей"""
    try:
        # Получаем статистику очередей
        stats = await task_manager.get_queue_stats()
        
        # Проверяем наличие воркеров
        worker_stats = await task_manager.get_worker_stats()
        worker_count = worker_stats.get("total_workers", 0)
        
        return {
            "status": "healthy" if worker_count > 0 else "unhealthy",
            "worker_count": worker_count,
            "queue_stats": stats,
            "checked_at": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
            "checked_at": datetime.utcnow().isoformat()
        }

async def gather_system_statistics() -> Dict[str, Any]:
    """Сбор статистики системы"""
    try:
        async with get_async_session() as session:
            rag_documents_service = RAGDocumentsService(session)
            rag_chunks_service = RAGChunksService(session)
            
            # Статистика документов
            total_documents = await rag_documents_service.count_documents()
            ready_documents = await rag_documents_service.count_documents_by_status("ready")
            processing_documents = await rag_documents_service.count_documents_by_status("processing")
            failed_documents = await rag_documents_service.count_documents_by_status("failed")
            
            # Статистика чанков
            total_chunks = await rag_chunks_service.count_chunks()
            
            # Статистика очередей
            queue_stats = await task_manager.get_queue_stats()
            
            return {
                "documents": {
                    "total": total_documents,
                    "ready": ready_documents,
                    "processing": processing_documents,
                    "failed": failed_documents
                },
                "chunks": {
                    "total": total_chunks
                },
                "queues": queue_stats,
                "collected_at": datetime.utcnow().isoformat()
            }
    except Exception as e:
        logger.error(f"Failed to gather system statistics: {e}")
        return {"error": str(e)}

async def cleanup_old_task_info() -> int:
    """Очистка устаревшей информации о задачах"""
    try:
        # Получаем все ключи задач
        task_keys = asyncio.run(redis_manager.keys_async("task_info:*"))
        
        cleaned_count = 0
        cutoff_time = datetime.utcnow() - timedelta(days=7)  # 7 дней
        
        for key in task_keys:
            try:
                task_info = asyncio.run(redis_manager.get_async(key))
                if task_info and isinstance(task_info, dict):
                    created_at = task_info.get("created_at")
                    if created_at:
                        task_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                        if task_time < cutoff_time:
                            asyncio.run(redis_manager.delete_async(key))
                            cleaned_count += 1
            except Exception as e:
                logger.error(f"Failed to cleanup task key {key}: {e}")
                continue
        
        return cleaned_count
    except Exception as e:
        logger.error(f"Failed to cleanup old task info: {e}")
        return 0

async def get_failed_documents() -> List[str]:
    """Получение документов со статусом 'failed'"""
    try:
        async with get_async_session() as session:
            rag_documents_service = RAGDocumentsService(session)
            failed_docs = await rag_documents_service.get_documents_by_status("failed")
            return [str(doc.id) for doc in failed_docs]
    except Exception as e:
        logger.error(f"Failed to get failed documents: {e}")
        return []

async def reset_document_status(document_id: str, status: str) -> bool:
    """Сброс статуса документа"""
    try:
        async with get_async_session() as session:
            rag_documents_service = RAGDocumentsService(session)
            success = await rag_documents_service.update_document_status(
                document_id=document_id,
                status=status,
                error_message=None
            )
            return success
    except Exception as e:
        logger.error(f"Failed to reset document status: {e}")
        return False
