"""
RAG Status Manager - управление статусами этапов обработки документов
"""
from __future__ import annotations
from typing import Dict, List, Optional, Any, Set
from uuid import UUID
from datetime import datetime, timezone
from enum import Enum
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.repositories.rag_status_repo import AsyncRAGStatusRepository
from app.repositories.factory import AsyncRepositoryFactory
from app.services.status_aggregator import calculate_aggregate_status
from app.models.rag import RAGDocument
from sqlalchemy import select, update

logger = get_logger(__name__)


class StageStatus(str, Enum):
    """Статусы этапов обработки"""
    PENDING = "pending"        # Ожидает запуска
    QUEUED = "queued"          # В очереди Celery
    PROCESSING = "processing"  # Выполняется
    COMPLETED = "completed"    # Успешно завершён
    FAILED = "failed"          # Завершён с ошибкой
    CANCELLED = "cancelled"    # Отменён пользователем


class PipelineStage(str, Enum):
    """Этапы pipeline обработки"""
    UPLOAD = "upload"
    EXTRACT = "extract"
    NORMALIZE = "normalize"
    CHUNK = "chunk"
    # embed этапы динамические: embed.<model_id>
    # index этапы динамические: index.<model_id>


class StatusTransitionError(Exception):
    """Ошибка при невалидном переходе статуса"""
    pass


# Валидные переходы между статусами
VALID_TRANSITIONS: Dict[StageStatus, Set[StageStatus]] = {
    StageStatus.PENDING: {StageStatus.QUEUED, StageStatus.PROCESSING, StageStatus.FAILED, StageStatus.CANCELLED},
    StageStatus.QUEUED: {StageStatus.PROCESSING, StageStatus.CANCELLED},
    StageStatus.PROCESSING: {StageStatus.COMPLETED, StageStatus.FAILED, StageStatus.CANCELLED},
    StageStatus.COMPLETED: {StageStatus.QUEUED},
    StageStatus.FAILED: {StageStatus.QUEUED, StageStatus.CANCELLED},
    StageStatus.CANCELLED: {StageStatus.QUEUED},
}


class RAGStatusManager:
    """
    Менеджер статусов RAG документов
    
    Отвечает за:
    - Валидацию переходов статусов
    - Обновление статусов в БД (через репозиторий)
    - Публикацию событий в Redis
    - Cascade обновления зависимых этапов
    """
    
    def __init__(
        self,
        session: AsyncSession,
        repo_factory: AsyncRepositoryFactory,
        event_publisher: Optional[Any] = None  # RAGEventPublisher
    ):
        self.session = session
        self.repo_factory = repo_factory
        self.status_repo = AsyncRAGStatusRepository(session)
        self.event_publisher = event_publisher
    
    async def initialize_document_statuses(
        self,
        doc_id: UUID,
        tenant_id: UUID,
        embed_models: List[str]
    ) -> None:
        """
        Инициализация статусов при создании документа
        
        Args:
            doc_id: ID документа
            tenant_id: ID тенанта
            embed_models: Список моделей эмбеддинга тенанта
        """
        logger.info(f"Initializing statuses for document {doc_id}")
        
        # Upload всегда completed сразу (файл уже загружен)
        await self.status_repo.upsert_node(
            doc_id=doc_id,
            node_type='pipeline',
            node_key=PipelineStage.UPLOAD.value,
            status=StageStatus.COMPLETED.value,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc)
        )
        
        # Остальные pipeline этапы в pending
        for stage in [PipelineStage.EXTRACT, PipelineStage.NORMALIZE, PipelineStage.CHUNK]:
            await self.status_repo.upsert_node(
                doc_id=doc_id,
                node_type='pipeline',
                node_key=stage.value,
                status=StageStatus.PENDING.value
            )
        
        # Embedding этапы для каждой модели в pending
        for model in embed_models:
            await self.status_repo.upsert_node(
                doc_id=doc_id,
                node_type='embedding',
                node_key=model,
                status=StageStatus.PENDING.value
            )
        
        # Index этапы для каждой модели в pending
        for model in embed_models:
            await self.status_repo.upsert_node(
                doc_id=doc_id,
                node_type='index',
                node_key=model,
                status=StageStatus.PENDING.value
            )
        
        # Публикуем событие инициализации
        if self.event_publisher:
            await self.event_publisher.publish_status_initialized(
                doc_id=doc_id,
                tenant_id=tenant_id
            )
        
        # Пересчитать агрегированный статус (будет 'uploaded')
        await self._update_aggregate_status(doc_id)
        
        logger.info(f"Initialized {4 + len(embed_models) * 2} status nodes for document {doc_id}")
    
    async def transition_stage(
        self,
        doc_id: UUID,
        stage: str,
        new_status: StageStatus,
        error: Optional[str] = None,
        metrics: Optional[Dict[str, Any]] = None,
        celery_task_id: Optional[str] = None
    ) -> None:
        """
        Изменить статус этапа с валидацией
        
        Args:
            doc_id: ID документа
            stage: Название этапа (extract, chunk, embed.model_id)
            new_status: Новый статус
            error: Сообщение об ошибке (если failed)
            metrics: Метрики этапа
            celery_task_id: ID Celery задачи
        """
        # Получаем текущий статус
        if stage.startswith('embed.'):
            node_type = 'embedding'
            node_key = stage.replace('embed.', '')
        elif stage.startswith('index.'):
            node_type = 'index'
            node_key = stage.replace('index.', '')
        else:
            node_type = 'pipeline'
            node_key = stage
        
        current_node = await self.status_repo.get_node(doc_id, node_type, node_key)
        
        if current_node:
            try:
                current_status = StageStatus(current_node.status)
            except Exception:
                legacy_map = {
                    'running': StageStatus.PROCESSING,
                    'ok': StageStatus.COMPLETED,
                    'error': StageStatus.FAILED,
                }
                mapped = legacy_map.get(str(current_node.status))
                if mapped is None:
                    current_status = None
                else:
                    current_status = mapped
            
            if current_status is not None:
                if new_status not in VALID_TRANSITIONS.get(current_status, set()):
                    raise StatusTransitionError(
                        f"Invalid transition: {current_status} -> {new_status} for stage {stage}"
                    )
        
        # Обновляем статус
        update_data = {
            'doc_id': doc_id,
            'node_type': node_type,
            'node_key': node_key,
            'status': new_status.value,
        }
        
        if error:
            update_data['error_short'] = error
        
        if metrics:
            update_data['metrics_json'] = metrics
        
        # Временные метки
        if new_status == StageStatus.PROCESSING:
            update_data['started_at'] = datetime.now(timezone.utc)
        elif new_status in [StageStatus.COMPLETED, StageStatus.FAILED, StageStatus.CANCELLED]:
            update_data['finished_at'] = datetime.now(timezone.utc)
        
        await self.status_repo.upsert_node(**update_data)
        
        # Публикуем событие
        if self.event_publisher:
            # Получаем tenant_id из документа
            from app.models.rag import RAGDocument
            
            result = await self.session.execute(
                select(RAGDocument.tenant_id).where(RAGDocument.id == doc_id)
            )
            tenant_id = result.scalar_one_or_none()
            
            await self.event_publisher.publish_status_update(
                doc_id=doc_id,
                tenant_id=tenant_id,
                stage=stage,
                status=new_status.value,
                error=error,
                metrics=metrics
            )
        
        # Cascade обновления при ошибке или отмене
        if new_status in [StageStatus.FAILED, StageStatus.CANCELLED]:
            await self._cascade_reset_downstream(doc_id, stage)
        
        # Пересчитать агрегированный статус документа
        await self._update_aggregate_status(doc_id)
        
        logger.info(f"Status transition: {doc_id} - {stage} -> {new_status.value}")
    
    async def start_ingest(self, doc_id: UUID) -> None:
        """
        Запустить инжест: перевести все pending этапы в queued
        
        Args:
            doc_id: ID документа
        """
        logger.info(f"Starting ingest for document {doc_id}")
        
        # Получаем все этапы в pending
        pipeline_nodes = await self.status_repo.get_pipeline_nodes(doc_id)
        embedding_nodes = await self.status_repo.get_embedding_nodes(doc_id)
        index_nodes = await self.status_repo.get_index_nodes(doc_id)
        
        if not pipeline_nodes and not embedding_nodes and not index_nodes:
            result = await self.session.execute(select(RAGDocument).where(RAGDocument.id == doc_id))
            document = result.scalar_one_or_none()
            tenant_id = document.tenant_id if document else None
            embed_models = await self._get_target_models(doc_id)
            if tenant_id is not None:
                await self.initialize_document_statuses(doc_id, tenant_id, embed_models)
                pipeline_nodes = await self.status_repo.get_pipeline_nodes(doc_id)
                embedding_nodes = await self.status_repo.get_embedding_nodes(doc_id)
                index_nodes = await self.status_repo.get_index_nodes(doc_id)
        
        # Переводим в queued
        for node in pipeline_nodes + embedding_nodes + index_nodes:
            if node.status == StageStatus.PENDING.value:
                await self.transition_stage(
                    doc_id=doc_id,
                    stage=(
                        node.node_key if node.node_type == 'pipeline'
                        else (f"embed.{node.node_key}" if node.node_type == 'embedding' else f"index.{node.node_key}")
                    ),
                    new_status=StageStatus.QUEUED
                )
        
        logger.info(f"Ingest started for document {doc_id}")
    
    async def stop_stage(self, doc_id: UUID, stage: str) -> Optional[str]:
        """
        Остановить выполнение этапа
        
        Args:
            doc_id: ID документа
            stage: Название этапа
            
        Returns:
            celery_task_id если нужно убить задачу, иначе None
        """
        logger.info(f"Stopping stage {stage} for document {doc_id}")
        
        if stage.startswith('embed.'):
            node_type = 'embedding'
            node_key = stage.replace('embed.', '')
        elif stage.startswith('index.'):
            node_type = 'index'
            node_key = stage.replace('index.', '')
        else:
            node_type = 'pipeline'
            node_key = stage
        
        current_node = await self.status_repo.get_node(doc_id, node_type, node_key)
        
        if not current_node:
            logger.warning(f"Stage {stage} not found for document {doc_id}")
            return None
        
        # Переводим в cancelled
        await self.transition_stage(
            doc_id=doc_id,
            stage=stage,
            new_status=StageStatus.CANCELLED
        )
        
        # Cascade: останавливаем последующие этапы
        await self._cascade_reset_downstream(doc_id, stage)
        
        # Возвращаем task_id если нужно убить задачу
        # TODO: добавить поле celery_task_id в модель
        return None
    
    async def retry_stage(self, doc_id: UUID, stage: str) -> None:
        """
        Перезапустить этап (failed/cancelled -> queued)
        
        Args:
            doc_id: ID документа
            stage: Название этапа
        """
        logger.info(f"Retrying stage {stage} for document {doc_id}")

        await self.transition_stage(
            doc_id=doc_id,
            stage=stage,
            new_status=StageStatus.QUEUED,
        )

        if stage.startswith('embed.'):
            model_key = stage.replace('embed.', '')
            await self._reset_stage_if_needed(
                doc_id,
                f'index.{model_key}',
                StageStatus.PENDING,
                force=True,
            )
            return

        if stage.startswith('index.'):
            return

        await self._cascade_reset_downstream(doc_id, stage, reset_to_pending=True)

    async def archive_document(self, doc_id: UUID) -> None:
        """Архивировать документ."""
        logger.info(f"Archiving document {doc_id}")

        await self.status_repo.upsert_node(
            doc_id=doc_id,
            node_type='archive',
            node_key='archive',
            status=StageStatus.COMPLETED.value,
            started_at=datetime.now(timezone.utc),
            finished_at=datetime.now(timezone.utc),
        )

    async def unarchive_document(self, doc_id: UUID) -> None:
        """Разархивировать документ."""
        logger.info(f"Unarchiving document {doc_id}")

        await self.status_repo.delete_node(doc_id, 'archive', 'archive')

    async def get_document_status(self, doc_id: UUID) -> Dict[str, Any]:
        """Получить полный статус документа."""
        pipeline_nodes = await self.status_repo.get_pipeline_nodes(doc_id)
        embedding_nodes = await self.status_repo.get_embedding_nodes(doc_id)

        result = {
            'document_id': str(doc_id),
            'pipeline': {},
            'embeddings': {},
            'archived': False,
        }

        for node in pipeline_nodes:
            result['pipeline'][node.node_key] = {
                'status': node.status,
                'error': node.error_short,
                'metrics': node.metrics_json,
                'started_at': node.started_at.isoformat() if node.started_at else None,
                'finished_at': node.finished_at.isoformat() if node.finished_at else None,
                'updated_at': node.updated_at.isoformat(),
            }

        for node in embedding_nodes:
            result['embeddings'][node.node_key] = {
                'status': node.status,
                'model_version': node.model_version,
                'error': node.error_short,
                'metrics': node.metrics_json,
                'started_at': node.started_at.isoformat() if node.started_at else None,
                'finished_at': node.finished_at.isoformat() if node.finished_at else None,
                'updated_at': node.updated_at.isoformat(),
            }

        archive_node = await self.status_repo.get_node(doc_id, 'archive', 'archive')
        if archive_node:
            result['archived'] = True

        return result

    async def _cascade_reset_downstream(
        self,
        doc_id: UUID,
        failed_stage: str,
        reset_to_pending: bool = False,
    ) -> None:
        """Сбросить статусы последующих этапов при ошибке или отмене."""
        target_status = StageStatus.PENDING if reset_to_pending else StageStatus.CANCELLED

        if failed_stage.startswith('embed.'):
            model = failed_stage.replace('embed.', '')
            await self._reset_stage_if_needed(
                doc_id,
                f'index.{model}',
                target_status,
                force=target_status == StageStatus.PENDING,
            )
            return

        if failed_stage.startswith('index.'):
            return

        stage_order = ['upload', 'extract', 'normalize', 'chunk']

        if failed_stage not in stage_order:
            return

        failed_index = stage_order.index(failed_stage)

        for stage_name in stage_order[failed_index + 1:]:
            await self._reset_stage_if_needed(
                doc_id,
                stage_name,
                target_status,
                force=target_status == StageStatus.PENDING,
            )

        embedding_nodes = await self.status_repo.get_embedding_nodes(doc_id)
        for node in embedding_nodes:
            await self._reset_stage_if_needed(
                doc_id,
                f'embed.{node.node_key}',
                target_status,
                force=target_status == StageStatus.PENDING,
            )
            await self._reset_stage_if_needed(
                doc_id,
                f'index.{node.node_key}',
                target_status,
                force=target_status == StageStatus.PENDING,
            )

    async def _reset_stage_if_needed(
        self,
        doc_id: UUID,
        stage: str,
        target_status: StageStatus,
        force: bool = False,
    ) -> None:
        """Сбросить статус этапа, если он не в финальном состоянии."""
        if stage.startswith('embed.'):
            node_type = 'embedding'
            node_key = stage.replace('embed.', '')
        elif stage.startswith('index.'):
            node_type = 'index'
            node_key = stage.replace('index.', '')
        else:
            node_type = 'pipeline'
            node_key = stage

        current_node = await self.status_repo.get_node(doc_id, node_type, node_key)

        if current_node:
            if not force and current_node.status in (
                StageStatus.COMPLETED.value,
                StageStatus.CANCELLED.value,
            ):
                return

            current_node.status = target_status.value
            if target_status == StageStatus.PENDING:
                current_node.started_at = None
                current_node.finished_at = None
                current_node.error_short = None
                current_node.metrics_json = None
            elif target_status == StageStatus.CANCELLED:
                current_node.finished_at = datetime.now(timezone.utc)
            current_node.updated_at = datetime.now(timezone.utc)
            await self.session.flush()
        else:
            await self.status_repo.upsert_node(
                doc_id=doc_id,
                node_type=node_type,
                node_key=node_key,
                status=target_status.value,
                started_at=None,
                finished_at=datetime.now(timezone.utc) if target_status == StageStatus.CANCELLED else None,
                error_short=None,
                metrics_json=None,
            )

    async def _update_aggregate_status(self, doc_id: UUID) -> None:
        """Пересчитать и обновить агрегированный статус документа."""
        pipeline_nodes = await self.status_repo.get_pipeline_nodes(doc_id)
        embedding_nodes = await self.status_repo.get_embedding_nodes(doc_id)
        index_nodes = await self.status_repo.get_index_nodes(doc_id)

        target_models = await self._get_target_models(doc_id)

        agg_status, agg_details = calculate_aggregate_status(
            doc_id=doc_id,
            pipeline_nodes=pipeline_nodes,
            embedding_nodes=embedding_nodes,
            target_models=target_models,
            index_nodes=index_nodes,
        )

        await self.session.execute(
            update(RAGDocument)
            .where(RAGDocument.id == doc_id)
            .values(
                agg_status=agg_status,
                agg_details_json=agg_details,
            )
        )

        logger.debug(f"Updated aggregate status for {doc_id}: {agg_status}")

    async def _get_target_models(self, doc_id: UUID) -> List[str]:
        """Получить список target-моделей для документа."""
        result = await self.session.execute(
            select(RAGDocument).where(RAGDocument.id == doc_id)
        )
        document = result.scalar_one_or_none()

        if not document:
            return []

        from app.models.tenant import Tenants

        result = await self.session.execute(
            select(Tenants).where(Tenants.id == document.tenant_id)
        )
        tenant = result.scalar_one_or_none()

        if not tenant:
            return []

        # Resolve global embedding + optional extra
        from app.models.model_registry import ModelRegistry, ModelType, ModelStatus

        models: List[str] = []
        result = await self.session.execute(
            select(ModelRegistry).where(
                (ModelRegistry.type == ModelType.EMBEDDING) & 
                (ModelRegistry.default_for_type == True) &
                (ModelRegistry.enabled == True)
            )
        )
        global_embed = result.scalars().first()
        if global_embed and global_embed.status == ModelStatus.AVAILABLE:
            models.append(global_embed.alias)

        if tenant.embedding_model_alias and tenant.embedding_model_alias not in models:
            models.append(tenant.embedding_model_alias)

        return models
