"""
RAG Status Manager - управление статусами этапов обработки документов
"""
from __future__ import annotations
from typing import Dict, List, Optional, Any
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import StatusTransitionError
from app.core.logging import get_logger
from app.repositories.rag_status_repo import AsyncRAGStatusRepository
from app.repositories.factory import AsyncRepositoryFactory
from app.services.status_aggregator import calculate_aggregate_status
from app.services.rag_target_model_service import RAGTargetModelService
from app.services.rag_status_views import build_document_status, build_ingest_policy
from app.services.rag_status_policy import (
    PipelineStage,
    StageStatus,
    VALID_TRANSITIONS,
    build_stage_control,
    format_stage_name,
    is_retry_supported,
    split_stage_name,
)
from app.models.rag import RAGDocument
from sqlalchemy import select, update

logger = get_logger(__name__)


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
        self.target_models = RAGTargetModelService(session, repo_factory)
        self.event_publisher = event_publisher

    @staticmethod
    def _format_stage_name(node_type: str, node_key: str) -> str:
        """Convert status node identity into public stage slug."""
        return format_stage_name(node_type, node_key)

    @staticmethod
    def _split_stage_name(stage: str) -> tuple[str, str]:
        """Convert public stage slug into node_type/node_key."""
        return split_stage_name(stage)

    @staticmethod
    def is_retry_supported(stage: str) -> bool:
        """Check whether the platform supports direct retry dispatch for a stage."""
        return is_retry_supported(stage)
    
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
        node_type, node_key = self._split_stage_name(stage)
        
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
        
        if celery_task_id:
            update_data['celery_task_id'] = celery_task_id
        
        if error:
            update_data['error_short'] = error
        
        if metrics:
            update_data['metrics_json'] = metrics
        
        # Временные метки
        if new_status == StageStatus.PROCESSING:
            update_data['started_at'] = datetime.now(timezone.utc)
        elif new_status in [StageStatus.COMPLETED, StageStatus.FAILED, StageStatus.CANCELLED]:
            update_data['finished_at'] = datetime.now(timezone.utc)
            # Clear task_id when stage finishes
            update_data['celery_task_id'] = None
        
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
    
    async def check_ingest_allowed(self, doc_id: UUID) -> Dict[str, Any]:
        policy = await self.get_ingest_policy(doc_id)
        if not policy["start_allowed"]:
            return {
                "allowed": False,
                "reason": policy.get("start_reason"),
                "active_stages": policy.get("active_stages", []),
            }
        return {"allowed": True}

    async def get_ingest_policy(self, doc_id: UUID) -> Dict[str, Any]:
        return await build_ingest_policy(self.status_repo, self.target_models, doc_id)

    def _build_stage_control(
        self,
        stage: str,
        node_type: str,
        status: str,
        archived: bool,
    ) -> Dict[str, Any]:
        """Derive control capabilities for a single stage."""
        return build_stage_control(
            stage=stage,
            node_type=node_type,
            status=status,
            archived=archived,
        )

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
        
        # Reset pipeline/model stages for a fresh run.
        # Important: rerun after completed ingest must not keep extract=completed,
        # otherwise worker transition completed->processing becomes invalid.
        for node in pipeline_nodes:
            if node.node_key == PipelineStage.UPLOAD.value:
                continue
            await self._reset_stage_if_needed(
                doc_id,
                node.node_key,
                StageStatus.PENDING,
                force=True,
            )

        for node in embedding_nodes:
            await self._reset_stage_if_needed(
                doc_id,
                f"embed.{node.node_key}",
                StageStatus.PENDING,
                force=True,
            )

        for node in index_nodes:
            await self._reset_stage_if_needed(
                doc_id,
                f"index.{node.node_key}",
                StageStatus.PENDING,
                force=True,
            )

        # Kick off from extract stage only. Downstream stages are picked by the chain.
        await self.transition_stage(
            doc_id=doc_id,
            stage=PipelineStage.EXTRACT.value,
            new_status=StageStatus.QUEUED,
        )
        
        logger.info(f"Ingest started for document {doc_id}")

    async def dispatch_ingest_pipeline(self, doc_id: UUID, tenant_id: UUID) -> List[str]:
        """Enqueue the full ingest pipeline for a document."""
        from app.workers.tasks_rag_ingest import (
            extract_document,
            normalize_document,
            chunk_document,
            embed_chunks_model,
            index_model,
        )
        from celery import chain, group
        embedding_models = await self._get_target_models(doc_id)
        if not embedding_models:
            raise ValueError(
                f"No embedding models configured for tenant {tenant_id}. "
                "Configure embedding models in Admin (models + defaults/tenant overrides)."
            )

        extract_task = extract_document.s(str(doc_id), str(tenant_id))
        normalize_task = normalize_document.s(str(tenant_id))
        chunk_task = chunk_document.s(str(tenant_id))

        embedding_index_chains = [
            chain(
                embed_chunks_model.s(str(tenant_id), model_alias),
                index_model.s(str(tenant_id)),
            )
            for model_alias in embedding_models
        ]

        pipeline = chain(extract_task, normalize_task, chunk_task, group(embedding_index_chains))
        pipeline.apply_async()
        return embedding_models
    
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
        
        node_type, node_key = self._split_stage_name(stage)
        
        current_node = await self.status_repo.get_node(doc_id, node_type, node_key)
        
        if not current_node:
            logger.warning(f"Stage {stage} not found for document {doc_id}")
            return None
        
        # Сохраняем task_id до перехода статуса
        task_id = getattr(current_node, 'celery_task_id', None)
        
        # Переводим в cancelled
        await self.transition_stage(
            doc_id=doc_id,
            stage=stage,
            new_status=StageStatus.CANCELLED
        )
        
        # Cascade: останавливаем последующие этапы
        await self._cascade_reset_downstream(doc_id, stage)
        
        # Возвращаем task_id для отмены в Celery
        return task_id
    
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
            model_key = stage.replace('embed.', '', 1)  # Только первое вхождение
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

    async def dispatch_stage_retry(self, doc_id: UUID, tenant_id: UUID, stage: str) -> None:
        """Enqueue concrete retry execution for a supported stage."""
        from app.workers.tasks_rag_ingest import embed_chunks_model, index_model

        if stage == "extract":
            await self.dispatch_ingest_pipeline(doc_id, tenant_id)
            return

        if stage.startswith("embed."):
            model_alias = stage.split(".", 1)[1]
            embed_chunks_model.delay({"source_id": str(doc_id)}, str(tenant_id), model_alias)
            return

        if stage.startswith("index."):
            model_alias = stage.split(".", 1)[1]
            index_model.delay({"source_id": str(doc_id), "model_alias": model_alias}, str(tenant_id))
            return

        raise ValueError(f"Retry dispatch is not supported for stage '{stage}'")

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
        return await build_document_status(self.status_repo, doc_id)

    async def _cascade_reset_downstream(
        self,
        doc_id: UUID,
        failed_stage: str,
        reset_to_pending: bool = False,
    ) -> None:
        """Сбросить статусы последующих этапов при ошибке или отмене."""
        target_status = StageStatus.PENDING if reset_to_pending else StageStatus.CANCELLED

        if failed_stage.startswith('embed.'):
            model = failed_stage.replace('embed.', '', 1)  # Только первое вхождение
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
        node_type, node_key = self._split_stage_name(stage)

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

        # Получаем tenant_id для публикации события
        result = await self.session.execute(
            select(RAGDocument.tenant_id).where(RAGDocument.id == doc_id)
        )
        tenant_id = result.scalar_one_or_none()

        await self.session.execute(
            update(RAGDocument)
            .where(RAGDocument.id == doc_id)
            .values(
                agg_status=agg_status,
                agg_details_json=agg_details,
            )
        )

        # Публикуем событие с agg_status для обновления UI
        if self.event_publisher and tenant_id:
            await self.event_publisher.publish_aggregate_status(
                doc_id=doc_id,
                tenant_id=tenant_id,
                agg_status=agg_status,
                agg_details=agg_details,
            )

        await self._refresh_collection_statuses_for_document(doc_id)

        logger.debug(f"Updated aggregate status for {doc_id}: {agg_status}")

    async def _refresh_collection_statuses_for_document(self, doc_id: UUID) -> None:
        """Refresh document collection readiness for collections that contain the document."""
        from sqlalchemy import text
        from app.services.collection_service import CollectionService

        result = await self.session.execute(
            text(
                "SELECT c.id "
                "FROM collections c "
                "JOIN sources src "
                "ON ((src.meta #>> '{collection,id}') = c.id::text OR (src.meta ->> 'collection_id') = c.id::text) "
                "WHERE src.source_id = :doc_id"
            ),
            {"doc_id": doc_id},
        )
        collection_ids = [row.id for row in result.mappings().all()]
        if not collection_ids:
            return

        collection_service = CollectionService(self.session)
        for collection_id in collection_ids:
            collection = await collection_service.get_by_id(collection_id)
            if collection:
                await collection_service.sync_collection_status(collection, persist=False)

    async def _get_target_models(self, doc_id: UUID) -> List[str]:
        """Получить список target-моделей для документа."""
        return await self.target_models.get_target_models(doc_id)

    async def get_target_models_for_tenant(self, tenant_id: UUID) -> List[str]:
        """Resolve effective embedding models for a tenant: global default + optional tenant-specific model."""
        return await self.target_models.get_target_models_for_tenant(tenant_id)
