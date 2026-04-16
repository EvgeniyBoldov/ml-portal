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
    Публикатор событий статусов RAG документов
    """
    
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
        
        await self._broadcast(event, tenant_id, f"status update: {doc_id} - {stage} -> {status}")
    
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
        
        await self._broadcast(event, tenant_id, f"status initialized: {doc_id}")
    
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
        
        await self._broadcast(event, tenant_id, f"ingest started: {doc_id}")
    
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
        
        await self._broadcast(event, tenant_id, f"aggregate status: {doc_id} -> {agg_status}")

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
        await self._broadcast(event, tenant_id, f"document {label}: {doc_id}")

    async def _broadcast(self, event: Dict[str, Any], tenant_id: UUID, label: str) -> None:
        """Publish event to admin, tenant, and legacy channels."""
        try:
            tenant_channel = self.CHANNEL_TENANT_FMT.format(tenant_id=str(tenant_id))
            payload = json.dumps(event)
            await self.redis.publish(self.CHANNEL_ADMIN, payload)
            await self.redis.publish(tenant_channel, payload)
            await self.redis.publish(self.CHANNEL_LEGACY, payload)
            logger.debug(f"Published {label}")
        except Exception as e:
            logger.error(f"Failed to publish {label}: {e}")


class RAGEventSubscriber:
    """
    Подписчик на события RAG статусов с фильтрацией
    
    Использует ОДИН канал Redis, но фильтрует события по tenant_id и role.
    """
    
    def __init__(self, redis_client: Any, tenant_id: Optional[UUID] = None, is_admin: bool = False):
        """
        Args:
            redis_client: Redis клиент
            tenant_id: ID тенанта для фильтрации (None для админа)
            is_admin: Флаг админа (видит все события)
        """
        self.redis = redis_client
        self.tenant_id = str(tenant_id) if tenant_id else None
        self.is_admin = is_admin
        self.pubsub = None
        if self.is_admin:
            self.channel = RAGEventPublisher.CHANNEL_ADMIN
        else:
            if not self.tenant_id:
                raise ValueError("tenant_id is required for non-admin subscriber")
            self.channel = RAGEventPublisher.CHANNEL_TENANT_FMT.format(tenant_id=self.tenant_id)
    
    async def subscribe(self):
        """Подписаться на канал событий"""
        self.pubsub = self.redis.pubsub()
        await self.pubsub.subscribe(self.channel)
        logger.info(f"Subscribed to {self.channel} (tenant={self.tenant_id}, admin={self.is_admin})")
    
    async def listen(self):
        """
        Слушать события с фильтрацией
        
        Yields:
            Отфильтрованные события
        """
        if not self.pubsub:
            await self.subscribe()
        
        async for message in self.pubsub.listen():
            if message['type'] != 'message':
                continue
            
            try:
                event = json.loads(message['data'])
                yield event
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode event: {e}")
            except Exception as e:
                logger.error(f"Error processing event: {e}")
    
    async def unsubscribe(self):
        """Отписаться от канала"""
        if self.pubsub:
            await self.pubsub.unsubscribe(self.channel)
            await self.pubsub.close()
            logger.info(f"Unsubscribed from {self.channel}")
