"""
RAG Event Publisher - публикация событий статусов в Redis
"""
from __future__ import annotations
from typing import Dict, Any, Optional
from uuid import UUID
from datetime import datetime, timezone
import json

from app.core.logging import get_logger
from app.schemas.rag_events import (
    RAGSSEEventType,
    RAGStatusUpdatePayload,
    RAGStatusInitializedPayload,
    RAGIngestStartedPayload,
    RAGAggregateUpdatePayload,
    RAGDocumentArchivedPayload,
    build_rag_event,
)

logger = get_logger(__name__)


class RAGEventPublisher:
    """
    Публикатор событий статусов RAG документов.

    Каналы Redis:
      rag:agg:admin                  — aggregate_update, document_archived/unarchived, document_added/deleted (admin)
      rag:agg:tenant:{tenant_id}     — то же, per-tenant
      rag:doc:{doc_id}               — все события конкретного документа (status_update + aggregate + lifecycle)

    Устаревшие каналы (rag:status:*) больше не используются.
    """

    CHANNEL_AGG_ADMIN = "rag:agg:admin"
    CHANNEL_AGG_TENANT_FMT = "rag:agg:tenant:{tenant_id}"
    CHANNEL_DOC_FMT = "rag:doc:{doc_id}"

    # Legacy — оставлены для обратной совместимости, будут удалены после полной миграции
    CHANNEL_LEGACY = "rag:status:updates"
    CHANNEL_ADMIN = "rag:status:admin"
    CHANNEL_TENANT_FMT = "rag:status:tenant:{tenant_id}"
    
    def __init__(self, redis_client: Optional[Any] = None):
        """
        Args:
            redis_client: Redis клиент (redis.asyncio.Redis)
        """
        self.redis = redis_client
        
        if not self.redis:
            logger.warning("RAGEventPublisher initialized without Redis client - events will not be published")
    
    async def publish_status_update(
        self,
        doc_id: UUID,
        tenant_id: UUID,
        stage: str,
        status: str,
        error: Optional[str] = None,
        metrics: Optional[Dict[str, Any]] = None,
        user_id: Optional[UUID] = None
    ) -> None:
        """
        Опубликовать событие обновления статуса
        
        Args:
            doc_id: ID документа
            tenant_id: ID тенанта (для фильтрации)
            stage: Название этапа
            status: Новый статус
            error: Сообщение об ошибке
            metrics: Метрики этапа
            user_id: ID пользователя который загрузил документ
        """
        if not self.redis:
            return
        
        event = build_rag_event(RAGStatusUpdatePayload(
            document_id=str(doc_id),
            tenant_id=str(tenant_id),
            user_id=str(user_id) if user_id else None,
            stage=stage,
            status=status,
            error=error,
            metrics=metrics or {},
            timestamp=datetime.now(timezone.utc).isoformat(),
        ))
        
        await self._broadcast_doc(event, doc_id, f"status update: {doc_id} - {stage} -> {status}")
    
    async def publish_status_initialized(
        self,
        doc_id: UUID,
        tenant_id: UUID,
        user_id: Optional[UUID] = None
    ) -> None:
        """
        Опубликовать событие инициализации статусов документа
        
        Args:
            doc_id: ID документа
            tenant_id: ID тенанта
            user_id: ID пользователя
        """
        if not self.redis:
            return
        
        event = build_rag_event(RAGStatusInitializedPayload(
            document_id=str(doc_id),
            tenant_id=str(tenant_id),
            user_id=str(user_id) if user_id else None,
            timestamp=datetime.now(timezone.utc).isoformat(),
        ))
        
        await self._broadcast_doc(event, doc_id, f"status initialized: {doc_id}")
    
    async def publish_ingest_started(
        self,
        doc_id: UUID,
        tenant_id: UUID,
        user_id: Optional[UUID] = None
    ) -> None:
        """
        Опубликовать событие начала инжеста
        
        Args:
            doc_id: ID документа
            tenant_id: ID тенанта
            user_id: ID пользователя
        """
        if not self.redis:
            return
        
        event = build_rag_event(RAGIngestStartedPayload(
            document_id=str(doc_id),
            tenant_id=str(tenant_id),
            user_id=str(user_id) if user_id else None,
            timestamp=datetime.now(timezone.utc).isoformat(),
        ))
        
        await self._broadcast_doc(event, doc_id, f"ingest started: {doc_id}")
    
    async def publish_aggregate_status(
        self,
        doc_id: UUID,
        tenant_id: UUID,
        agg_status: str,
        agg_details: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Опубликовать событие обновления агрегированного статуса документа
        
        Args:
            doc_id: ID документа
            tenant_id: ID тенанта
            agg_status: Агрегированный статус (pending, processing, ready, failed)
            agg_details: Детали статуса (pipeline stages, embeddings, etc.)
        """
        if not self.redis:
            return
        
        event = build_rag_event(RAGAggregateUpdatePayload(
            document_id=str(doc_id),
            tenant_id=str(tenant_id),
            agg_status=agg_status,
            agg_details=agg_details or {},
            timestamp=datetime.now(timezone.utc).isoformat(),
        ))
        # Legacy aliases for frontend backward compatibility
        event['status'] = agg_status
        event['effective_status'] = (agg_details or {}).get("effective_status")
        event['effective_reason'] = (agg_details or {}).get("effective_reason")
        
        await self._broadcast_agg_and_doc(event, tenant_id, doc_id, f"aggregate status: {doc_id} -> {agg_status}")

    async def publish_document_archived(
        self,
        doc_id: UUID,
        tenant_id: UUID,
        archived: bool
    ) -> None:
        """
        Опубликовать событие архивации/разархивации документа
        
        Args:
            doc_id: ID документа
            tenant_id: ID тенанта
            archived: True если архивирован, False если разархивирован
        """
        if not self.redis:
            return
        
        et = RAGSSEEventType.DOCUMENT_ARCHIVED if archived else RAGSSEEventType.DOCUMENT_UNARCHIVED
        event = build_rag_event(RAGDocumentArchivedPayload(
            document_id=str(doc_id),
            tenant_id=str(tenant_id),
            event_type=et.value,
            archived=archived,
            timestamp=datetime.now(timezone.utc).isoformat(),
        ))
        
        label = 'archived' if archived else 'unarchived'
        await self._broadcast_agg_and_doc(event, tenant_id, doc_id, f"document {label}: {doc_id}")

    async def publish_document_added(
        self,
        doc_id: UUID,
        tenant_id: UUID,
        collection_id: UUID,
    ) -> None:
        """Опубликовать событие добавления документа в коллекцию (или загрузки)."""
        if not self.redis:
            return
        event = {
            "event_type": "document_added",
            "document_id": str(doc_id),
            "tenant_id": str(tenant_id),
            "collection_id": str(collection_id),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await self._broadcast_agg_and_doc(event, tenant_id, doc_id, f"document added: {doc_id}")

    async def publish_document_deleted(
        self,
        doc_id: UUID,
        tenant_id: UUID,
        collection_id: UUID,
    ) -> None:
        """Опубликовать событие удаления документа из коллекции."""
        if not self.redis:
            return
        event = {
            "event_type": "document_deleted",
            "document_id": str(doc_id),
            "tenant_id": str(tenant_id),
            "collection_id": str(collection_id),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        await self._broadcast_agg_and_doc(event, tenant_id, doc_id, f"document deleted: {doc_id}")

    async def _broadcast_agg_and_doc(
        self, event: Dict[str, Any], tenant_id: UUID, doc_id: UUID, label: str
    ) -> None:
        """Publish to aggregate channels (admin + tenant) and per-document channel."""
        try:
            payload = json.dumps(event)
            agg_tenant_ch = self.CHANNEL_AGG_TENANT_FMT.format(tenant_id=str(tenant_id))
            doc_ch = self.CHANNEL_DOC_FMT.format(doc_id=str(doc_id))
            await self.redis.publish(self.CHANNEL_AGG_ADMIN, payload)
            await self.redis.publish(agg_tenant_ch, payload)
            await self.redis.publish(doc_ch, payload)
            logger.debug(f"Published {label}")
        except Exception as e:
            logger.error(f"Failed to publish {label}: {e}")

    async def _broadcast_doc(
        self, event: Dict[str, Any], doc_id: UUID, label: str
    ) -> None:
        """Publish only to per-document channel (e.g. status_update steps)."""
        try:
            payload = json.dumps(event)
            doc_ch = self.CHANNEL_DOC_FMT.format(doc_id=str(doc_id))
            await self.redis.publish(doc_ch, payload)
            logger.debug(f"Published {label}")
        except Exception as e:
            logger.error(f"Failed to publish {label}: {e}")

    async def _broadcast(self, event: Dict[str, Any], tenant_id: UUID, label: str) -> None:
        """Legacy broadcast — kept for backward compatibility. Use _broadcast_agg_and_doc instead."""
        try:
            tenant_channel = self.CHANNEL_TENANT_FMT.format(tenant_id=str(tenant_id))
            payload = json.dumps(event)
            await self.redis.publish(self.CHANNEL_ADMIN, payload)
            await self.redis.publish(tenant_channel, payload)
            logger.debug(f"Published (legacy) {label}")
        except Exception as e:
            logger.error(f"Failed to publish {label}: {e}")


class RAGEventSubscriber:
    """
    Подписчик на Redis-каналы RAG событий.

    Два режима:
      subscribe_aggregate(is_admin, tenant_id) — канал rag:agg:admin или rag:agg:tenant:{id}
      subscribe_document(doc_id)               — канал rag:doc:{doc_id}
    """

    def __init__(self, redis_client: Any, tenant_id: Optional[UUID] = None, is_admin: bool = False):
        self.redis = redis_client
        self.tenant_id = str(tenant_id) if tenant_id else None
        self.is_admin = is_admin
        self.pubsub = None
        self._channel: Optional[str] = None

        if self.is_admin:
            self._channel = RAGEventPublisher.CHANNEL_AGG_ADMIN
        else:
            if not self.tenant_id:
                raise ValueError("tenant_id is required for non-admin subscriber")
            self._channel = RAGEventPublisher.CHANNEL_AGG_TENANT_FMT.format(tenant_id=self.tenant_id)

    @classmethod
    def for_document(cls, redis_client: Any, doc_id: UUID) -> "RAGEventSubscriber":
        """Create subscriber for a specific document's per-step events."""
        inst = cls.__new__(cls)
        inst.redis = redis_client
        inst.tenant_id = None
        inst.is_admin = False
        inst.pubsub = None
        inst._channel = RAGEventPublisher.CHANNEL_DOC_FMT.format(doc_id=str(doc_id))
        return inst

    async def subscribe(self) -> None:
        """Subscribe to the configured channel."""
        self.pubsub = self.redis.pubsub()
        await self.pubsub.subscribe(self._channel)
        logger.info(f"Subscribed to {self._channel}")

    async def listen(self):
        """Yield decoded events from the subscribed channel."""
        if not self.pubsub:
            await self.subscribe()

        async for message in self.pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                yield json.loads(message["data"])
            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode SSE event: {e}")
            except Exception as e:
                logger.error(f"Error processing SSE event: {e}")

    async def unsubscribe(self) -> None:
        """Unsubscribe and close pubsub connection."""
        if self.pubsub:
            await self.pubsub.unsubscribe(self._channel)
            await self.pubsub.close()
            logger.info(f"Unsubscribed from {self._channel}")
