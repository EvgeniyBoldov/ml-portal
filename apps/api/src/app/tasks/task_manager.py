"""
Менеджер задач для ML Portal
Управление очередями, мониторинг и планирование задач
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Union
from uuid import UUID

from celery import Celery
from celery.result import AsyncResult
from celery.exceptions import Retry

from app.celery_app import app as celery_app
from app.core.redis import redis_manager
from app.core.db import get_async_session
from app.services.rag_service_enhanced import RAGDocumentsService
from app.tasks.bg_tasks_enhanced import (
    process_document,
    extract_and_normalize_text,
    chunk_document,
    generate_embeddings,
    finalize_document,
    analyze_document,
    cleanup_old_documents
)

logger = logging.getLogger(__name__)

class TaskManager:
    """Менеджер для управления фоновыми задачами"""
    
    def __init__(self):
        self.celery_app = celery_app
        self.redis = redis_manager
    
    # Управление задачами обработки документов
    
    async def process_document_async(self, document_id: str, source_key: Optional[str] = None, 
                                   priority: str = "normal") -> Dict[str, Any]:
        """
        Асинхронная обработка документа
        
        Args:
            document_id: ID документа
            source_key: Ключ файла в S3
            priority: Приоритет задачи (low, normal, high, critical)
        
        Returns:
            Информация о запущенной задаче
        """
        try:
            # Определяем очередь по приоритету
            queue_map = {
                "low": "rag_low",
                "normal": "upload_high", 
                "high": "upload_high",
                "critical": "chat_critical"
            }
            queue = queue_map.get(priority, "upload_high")
            
            # Запускаем задачу
            task = process_document.delay(document_id, source_key)
            
            # Сохраняем информацию о задаче
            task_info = {
                "task_id": task.id,
                "document_id": document_id,
                "status": "pending",
                "queue": queue,
                "priority": priority,
                "created_at": datetime.utcnow().isoformat(),
                "source_key": source_key
            }
            
            await self._save_task_info(task.id, task_info)
            
            logger.info(f"Document processing task started: {task.id} for document {document_id}")
            return task_info
            
        except Exception as e:
            logger.error(f"Failed to start document processing task: {e}")
            raise
    
    async def analyze_document_async(self, document_id: str, analysis_type: str = "summary",
                                   priority: str = "normal") -> Dict[str, Any]:
        """
        Асинхронный анализ документа
        
        Args:
            document_id: ID документа
            analysis_type: Тип анализа
            priority: Приоритет задачи
        
        Returns:
            Информация о запущенной задаче
        """
        try:
            queue = "analyze_medium" if priority == "normal" else "chat_critical"
            
            task = analyze_document.delay(document_id, analysis_type)
            
            task_info = {
                "task_id": task.id,
                "document_id": document_id,
                "analysis_type": analysis_type,
                "status": "pending",
                "queue": queue,
                "priority": priority,
                "created_at": datetime.utcnow().isoformat()
            }
            
            await self._save_task_info(task.id, task_info)
            
            logger.info(f"Document analysis task started: {task.id} for document {document_id}")
            return task_info
            
        except Exception as e:
            logger.error(f"Failed to start document analysis task: {e}")
            raise
    
    async def cleanup_old_documents_async(self, days_old: int = 30, 
                                        priority: str = "low") -> Dict[str, Any]:
        """
        Асинхронная очистка старых документов
        
        Args:
            days_old: Возраст документов для удаления
            priority: Приоритет задачи
        
        Returns:
            Информация о запущенной задаче
        """
        try:
            queue = "cleanup_low"
            
            task = cleanup_old_documents.delay(days_old)
            
            task_info = {
                "task_id": task.id,
                "days_old": days_old,
                "status": "pending",
                "queue": queue,
                "priority": priority,
                "created_at": datetime.utcnow().isoformat()
            }
            
            await self._save_task_info(task.id, task_info)
            
            logger.info(f"Cleanup task started: {task.id} for documents older than {days_old} days")
            return task_info
            
        except Exception as e:
            logger.error(f"Failed to start cleanup task: {e}")
            raise
    
    # Мониторинг задач
    
    async def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """
        Получение статуса задачи
        
        Args:
            task_id: ID задачи
        
        Returns:
            Статус задачи
        """
        try:
            # Получаем информацию из Redis
            task_info = await self._get_task_info(task_id)
            if not task_info:
                return {"error": "Task not found"}
            
            # Получаем статус из Celery
            result = AsyncResult(task_id, app=self.celery_app)
            
            status_info = {
                "task_id": task_id,
                "status": result.status,
                "result": result.result if result.successful() else None,
                "error": str(result.result) if result.failed() else None,
                "created_at": task_info.get("created_at"),
                "document_id": task_info.get("document_id"),
                "queue": task_info.get("queue"),
                "priority": task_info.get("priority")
            }
            
            # Обновляем статус в Redis
            task_info["status"] = result.status
            await self._save_task_info(task_id, task_info)
            
            return status_info
            
        except Exception as e:
            logger.error(f"Failed to get task status: {e}")
            return {"error": str(e)}
    
    async def get_document_tasks(self, document_id: str) -> List[Dict[str, Any]]:
        """
        Получение всех задач для документа
        
        Args:
            document_id: ID документа
        
        Returns:
            Список задач документа
        """
        try:
            # Получаем все задачи из Redis
            tasks = await self._get_document_tasks(document_id)
            return tasks
            
        except Exception as e:
            logger.error(f"Failed to get document tasks: {e}")
            return []
    
    async def cancel_task(self, task_id: str) -> bool:
        """
        Отмена задачи
        
        Args:
            task_id: ID задачи
        
        Returns:
            Успешность отмены
        """
        try:
            result = AsyncResult(task_id, app=self.celery_app)
            result.revoke(terminate=True)
            
            # Обновляем статус в Redis
            task_info = await self._get_task_info(task_id)
            if task_info:
                task_info["status"] = "revoked"
                await self._save_task_info(task_id, task_info)
            
            logger.info(f"Task {task_id} cancelled")
            return True
            
        except Exception as e:
            logger.error(f"Failed to cancel task {task_id}: {e}")
            return False
    
    # Планирование задач
    
    async def schedule_document_processing(self, document_ids: List[str], 
                                         priority: str = "normal",
                                         delay_seconds: int = 0) -> List[Dict[str, Any]]:
        """
        Планирование обработки нескольких документов
        
        Args:
            document_ids: Список ID документов
            priority: Приоритет задач
            delay_seconds: Задержка перед запуском в секундах
        
        Returns:
            Список информации о задачах
        """
        try:
            tasks_info = []
            
            for i, document_id in enumerate(document_ids):
                # Вычисляем задержку для каждой задачи
                task_delay = delay_seconds + (i * 5)  # 5 секунд между задачами
                
                if task_delay > 0:
                    # Планируем задачу с задержкой
                    task = process_document.apply_async(
                        args=[document_id],
                        countdown=task_delay
                    )
                else:
                    # Запускаем задачу немедленно
                    task = process_document.delay(document_id)
                
                task_info = {
                    "task_id": task.id,
                    "document_id": document_id,
                    "status": "scheduled" if task_delay > 0 else "pending",
                    "priority": priority,
                    "delay_seconds": task_delay,
                    "created_at": datetime.utcnow().isoformat()
                }
                
                await self._save_task_info(task.id, task_info)
                tasks_info.append(task_info)
            
            logger.info(f"Scheduled {len(document_ids)} document processing tasks")
            return tasks_info
            
        except Exception as e:
            logger.error(f"Failed to schedule document processing: {e}")
            raise
    
    async def schedule_cleanup(self, days_old: int = 30, 
                             schedule_time: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Планирование очистки старых документов
        
        Args:
            days_old: Возраст документов для удаления
            schedule_time: Время запуска (если None, то немедленно)
        
        Returns:
            Информация о запланированной задаче
        """
        try:
            if schedule_time:
                # Планируем задачу на определенное время
                eta = schedule_time
                task = cleanup_old_documents.apply_async(
                    args=[days_old],
                    eta=eta
                )
            else:
                # Запускаем задачу немедленно
                task = cleanup_old_documents.delay(days_old)
            
            task_info = {
                "task_id": task.id,
                "days_old": days_old,
                "status": "scheduled" if schedule_time else "pending",
                "priority": "low",
                "scheduled_for": schedule_time.isoformat() if schedule_time else None,
                "created_at": datetime.utcnow().isoformat()
            }
            
            await self._save_task_info(task.id, task_info)
            
            logger.info(f"Cleanup task scheduled: {task.id}")
            return task_info
            
        except Exception as e:
            logger.error(f"Failed to schedule cleanup: {e}")
            raise
    
    # Статистика и мониторинг
    
    async def get_queue_stats(self) -> Dict[str, Any]:
        """
        Получение статистики очередей
        
        Returns:
            Статистика очередей
        """
        try:
            inspect = self.celery_app.control.inspect()
            
            # Получаем статистику активных задач
            active = inspect.active()
            scheduled = inspect.scheduled()
            reserved = inspect.reserved()
            
            stats = {
                "queues": {},
                "total_active": 0,
                "total_scheduled": 0,
                "total_reserved": 0,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            # Обрабатываем активные задачи
            if active:
                for worker, tasks in active.items():
                    for task in tasks:
                        queue = task.get("delivery_info", {}).get("routing_key", "unknown")
                        if queue not in stats["queues"]:
                            stats["queues"][queue] = {"active": 0, "scheduled": 0, "reserved": 0}
                        stats["queues"][queue]["active"] += 1
                        stats["total_active"] += 1
            
            # Обрабатываем запланированные задачи
            if scheduled:
                for worker, tasks in scheduled.items():
                    for task in tasks:
                        queue = task.get("delivery_info", {}).get("routing_key", "unknown")
                        if queue not in stats["queues"]:
                            stats["queues"][queue] = {"active": 0, "scheduled": 0, "reserved": 0}
                        stats["queues"][queue]["scheduled"] += 1
                        stats["total_scheduled"] += 1
            
            # Обрабатываем зарезервированные задачи
            if reserved:
                for worker, tasks in reserved.items():
                    for task in tasks:
                        queue = task.get("delivery_info", {}).get("routing_key", "unknown")
                        if queue not in stats["queues"]:
                            stats["queues"][queue] = {"active": 0, "scheduled": 0, "reserved": 0}
                        stats["queues"][queue]["reserved"] += 1
                        stats["total_reserved"] += 1
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get queue stats: {e}")
            return {"error": str(e)}
    
    async def get_worker_stats(self) -> Dict[str, Any]:
        """
        Получение статистики воркеров
        
        Returns:
            Статистика воркеров
        """
        try:
            inspect = self.celery_app.control.inspect()
            
            # Получаем информацию о воркерах
            stats = inspect.stats()
            active_queues = inspect.active_queues()
            
            worker_info = {
                "workers": {},
                "total_workers": 0,
                "timestamp": datetime.utcnow().isoformat()
            }
            
            if stats:
                for worker, worker_stats in stats.items():
                    worker_info["workers"][worker] = {
                        "status": "online",
                        "total_tasks": worker_stats.get("total", {}),
                        "pool": worker_stats.get("pool", {}),
                        "rusage": worker_stats.get("rusage", {}),
                        "queues": active_queues.get(worker, []) if active_queues else []
                    }
                    worker_info["total_workers"] += 1
            
            return worker_info
            
        except Exception as e:
            logger.error(f"Failed to get worker stats: {e}")
            return {"error": str(e)}
    
    # Вспомогательные методы
    
    async def _save_task_info(self, task_id: str, task_info: Dict[str, Any]) -> None:
        """Сохранение информации о задаче в Redis"""
        try:
            key = f"task_info:{task_id}"
            await self.redis.set_async(key, task_info, expire=86400)  # 24 часа
            
            # Сохраняем связь задача -> документ
            if "document_id" in task_info:
                doc_key = f"document_tasks:{task_info['document_id']}"
                await self.redis.sadd_async(doc_key, task_id)
                await self.redis.expire_async(doc_key, 86400)
                
        except Exception as e:
            logger.error(f"Failed to save task info: {e}")
    
    async def _get_task_info(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Получение информации о задаче из Redis"""
        try:
            key = f"task_info:{task_id}"
            return await self.redis.get_async(key)
        except Exception as e:
            logger.error(f"Failed to get task info: {e}")
            return None
    
    async def _get_document_tasks(self, document_id: str) -> List[Dict[str, Any]]:
        """Получение всех задач документа"""
        try:
            doc_key = f"document_tasks:{document_id}"
            task_ids = await self.redis.smembers_async(doc_key)
            
            tasks = []
            for task_id in task_ids:
                task_info = await self._get_task_info(task_id)
                if task_info:
                    tasks.append(task_info)
            
            return tasks
        except Exception as e:
            logger.error(f"Failed to get document tasks: {e}")
            return []

# Глобальный экземпляр менеджера задач
task_manager = TaskManager()
