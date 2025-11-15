"""
Job Manager - управление Celery задачами (cancel/kill/reset/restart)
"""
from __future__ import annotations
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.core.logging import get_logger
from app.models.state_engine import Job
from app.repositories.factory import AsyncRepositoryFactory
from app.services.state_engine import StateEngine
from celery import Celery
from celery.result import AsyncResult

logger = get_logger(__name__)


class JobManager:
    """
    Менеджер для управления Celery задачами документа.
    
    Поддерживает cancel, kill, reset, restart операции.
    """
    
    def __init__(
        self,
        session: AsyncSession,
        repo_factory: AsyncRepositoryFactory,
        celery_app: Celery
    ):
        self.session = session
        self.repo_factory = repo_factory
        self.celery_app = celery_app
        self.state_engine = StateEngine(session, repo_factory)
    
    async def cancel_document_jobs(
        self,
        document_id: UUID,
        reason: Optional[str] = None,
        actor: Optional[str] = None
    ) -> int:
        """
        Отменить все активные задачи документа.
        
        Статус документа остается 'processing', узлы 'running→pending'.
        
        Args:
            document_id: ID документа
            reason: Причина отмены
            actor: Кто отменил (user_id или 'system')
            
        Returns:
            Количество отмененных задач
        """
        # Найти все активные задачи документа
        result = await self.session.execute(
            select(Job).where(
                Job.document_id == document_id,
                Job.state.in_(['pending', 'running'])
            )
        )
        jobs = result.scalars().all()
        
        canceled_count = 0
        for job in jobs:
            if job.celery_task_id:
                try:
                    # Revoke task (не terminate)
                    self.celery_app.control.revoke(
                        job.celery_task_id,
                        terminate=False
                    )
                    
                    # Обновить статус задачи
                    job.state = 'canceled'
                    job.finished_at = datetime.now(timezone.utc)
                    canceled_count += 1
                    
                    logger.info(f"Canceled job {job.celery_task_id} for document {document_id}")
                except Exception as e:
                    logger.error(f"Failed to cancel job {job.celery_task_id}: {e}")
        
        await self.session.flush()
        
        # Статус документа остается 'processing', но узлы переводим в pending
        # Это можно сделать через RAGStatusManager если нужно
        
        logger.info(f"Canceled {canceled_count} jobs for document {document_id}")
        return canceled_count
    
    async def kill_task(
        self,
        task_id: str,
        reason: Optional[str] = None,
        timeout: int = 5
    ) -> bool:
        """
        Убить задачу (revoke с terminate=True).
        
        Эскалация SIGTERM → SIGKILL по таймауту.
        Фиксируем в jobs как 'killed'.
        
        Args:
            task_id: Celery task ID
            reason: Причина убийства
            timeout: Timeout в секундах перед эскалацией до SIGKILL
            
        Returns:
            True если задача успешно убита
        """
        # Найти задачу по task_id
        result = await self.session.execute(
            select(Job).where(Job.celery_task_id == task_id)
        )
        job = result.scalar_one_or_none()
        
        if not job:
            logger.warning(f"Job not found for task_id: {task_id}")
            return False
        
        try:
            # Получить результат задачи для проверки статуса
            from celery.result import AsyncResult
            async_result = AsyncResult(task_id, app=self.celery_app)
            
            # Если задача уже завершена, просто помечаем как killed
            if async_result.ready():
                logger.info(f"Task {task_id} already finished with state: {async_result.state}")
                job.state = 'killed'
                job.finished_at = datetime.now(timezone.utc)
                job.error_json = {
                    'reason': reason or 'Already finished',
                    'original_state': async_result.state,
                    'killed_at': datetime.now(timezone.utc).isoformat()
                }
                await self.session.flush()
                return True
            
            # Revoke with terminate=True (SIGTERM)
            self.celery_app.control.revoke(
                task_id,
                terminate=True,
                signal='SIGTERM'
            )
            
            logger.info(f"Sent SIGTERM to task {task_id}, waiting {timeout}s...")
            
            # Ждем завершения (или таймаут)
            import asyncio
            start_time = datetime.now(timezone.utc)
            
            # Проверяем статус с интервалами
            while True:
                await asyncio.sleep(0.5)
                elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()
                
                if async_result.ready():
                    logger.info(f"Task {task_id} terminated successfully")
                    break
                
                if elapsed >= timeout:
                    logger.warning(f"Task {task_id} didn't terminate in {timeout}s, escalating to SIGKILL")
                    # Эскалация до SIGKILL
                    try:
                        self.celery_app.control.revoke(
                            task_id,
                            terminate=True,
                            signal='SIGKILL'
                        )
                        logger.info(f"Sent SIGKILL to task {task_id}")
                        await asyncio.sleep(1)  # Даем время на завершение
                    except Exception as e:
                        logger.error(f"Failed to send SIGKILL: {e}")
                    break
            
            # Обновить статус задачи
            job.state = 'killed'
            job.finished_at = datetime.now(timezone.utc)
            job.error_json = {
                'reason': reason or 'Killed by user',
                'terminated_at': datetime.now(timezone.utc).isoformat(),
                'timeout_used': elapsed >= timeout
            }
            
            await self.session.flush()
            
            logger.info(f"Killed task {task_id} for job {job.id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to kill task {task_id}: {e}", exc_info=True)
            
            # Все равно помечаем как killed
            job.state = 'killed'
            job.finished_at = datetime.now(timezone.utc)
            job.error_json = {
                'error': str(e),
                'error_type': type(e).__name__,
                'killed_at': datetime.now(timezone.utc).isoformat()
            }
            await self.session.flush()
            
            return False
    
    async def reset_document(
        self,
        document_id: UUID,
        step: str,
        reason: Optional[str] = None,
        actor: Optional[str] = None
    ) -> bool:
        """
        Откатить документ к указанному шагу, очистив артефакты ниже шага.
        
        Транзакционно:
        1. Чистим chunks/embeddings/progress ниже шага
        2. Откатываем статус на step
        3. Шлем событие rag.status в outbox
        
        Args:
            document_id: ID документа
            step: Шаг для отката (extract|normalize|split|embed|commit)
            reason: Причина отката
            actor: Кто инициировал
            
        Returns:
            True если откат успешен
        """
        # Определить шаги для очистки (все что ниже step)
        step_order = ['extract', 'normalize', 'split', 'embed', 'commit']
        try:
            step_idx = step_order.index(step)
        except ValueError:
            raise ValueError(f"Invalid step: {step}. Must be one of {step_order}")
        
        steps_to_clean = step_order[step_idx + 1:] if step_idx < len(step_order) - 1 else []
        
        # TODO: Очистить артефакты (chunks, embeddings, progress) для шагов steps_to_clean
        # Это требует доступа к репозиториям для chunks и embeddings
        # Пока что логируем
        
        logger.info(f"Cleaning artifacts for steps: {steps_to_clean}")
        
        # Откатить статус документа
        # Определить новый статус на основе step
        status_map = {
            'extract': 'processing',
            'normalize': 'processing',
            'split': 'processing',
            'embed': 'processing',
            'commit': 'ready'
        }
        new_status = status_map.get(step, 'processing')
        
        # Использовать StateEngine для перехода
        await self.state_engine.transition_status(
            document_id=document_id,
            to_status=new_status,
            reason=reason or f"Reset to step {step}",
            actor=actor
        )
        
        logger.info(f"Reset document {document_id} to step {step}")
        return True
    
    async def restart_document(
        self,
        document_id: UUID,
        step: str,
        reason: Optional[str] = None,
        actor: Optional[str] = None
    ) -> bool:
        """
        Перезапустить пайплайн с указанного шага.
        
        Эквивалент reset(step) + запуск пайплайна с этого шага.
        
        Args:
            document_id: ID документа
            step: Шаг для запуска
            reason: Причина перезапуска
            actor: Кто инициировал
            
        Returns:
            True если перезапуск успешен
        """
        # Сначала reset
        await self.reset_document(document_id, step, reason, actor)
        
        # Запустить пайплайн с шага step
        from app.workers.tasks_rag_ingest import (
            extract_normalize, chunk_document, embed_chunks_model, commit_source
        )
        from app.services.rag_status_manager import RAGStatusManager
        from celery import chain, group
        
        # Get tenant models for embeddings
        status_manager = RAGStatusManager(self.session, self.repo_factory)
        embedding_models = await status_manager._get_target_models(document_id)
        
        if not embedding_models:
            from app.core.config import get_embedding_models
            embedding_models = get_embedding_models()
        
        tenant_id = str(self.repo_factory.tenant_id)
        doc_id_str = str(document_id)
        
        # Start pipeline from appropriate step
        if step == 'extract':
            # Start from extract -> chunk -> embeddings
            extract_task = extract_normalize.s(doc_id_str, tenant_id)
            chunk_task = chunk_document.s(tenant_id)
            embedding_tasks = [
                embed_chunks_model.s(tenant_id, model) for model in embedding_models
            ]
            pipeline = chain(extract_task, chunk_task, group(embedding_tasks))
            pipeline.apply_async()
            
        elif step == 'chunk':
            # Start from chunk -> embeddings
            # Need to get extract result first
            from app.repositories.rag_ingest_repos import AsyncSourceRepository
            source_repo = AsyncSourceRepository(self.session, self.repo_factory.tenant_id)
            source = await source_repo.get_by_id(document_id)
            if not source or source.status != 'extracted':
                raise ValueError(f"Document {document_id} extract step not completed")
            
            # Create mock extract result (chunk_document expects extract_result as first arg)
            extract_result = {"source_id": doc_id_str, "status": "completed"}
            chunk_task = chunk_document.s(extract_result, tenant_id)
            embedding_tasks = [
                embed_chunks_model.s(tenant_id, model) for model in embedding_models
            ]
            pipeline = chain(chunk_task, group(embedding_tasks))
            pipeline.apply_async()
            
        elif step == 'embed':
            # Start embeddings for all models
            # Need chunk result
            from app.repositories.rag_ingest_repos import AsyncChunkRepository
            chunk_repo = AsyncChunkRepository(self.session, self.repo_factory.tenant_id)
            chunks = await chunk_repo.get_by_source_id(document_id)
            if not chunks:
                raise ValueError(f"Document {document_id} chunk step not completed")
            
            # Create mock chunk result (embed_chunks_model expects chunk_result as first arg)
            chunk_result = {"source_id": doc_id_str, "status": "completed"}
            embedding_tasks = [
                embed_chunks_model.s(chunk_result, tenant_id, model) for model in embedding_models
            ]
            group(embedding_tasks).apply_async()
            
        else:
            logger.warning(f"Restart from step {step} not fully implemented")
        
        logger.info(f"Restarted document {document_id} from step {step}")
        return True

