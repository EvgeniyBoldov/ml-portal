"""
RAG Event Publisher - публикация событий статусов в Redis
"""
from __future__ import annotations
from typing import Dict, Any, Optional
from uuid import UUID
from datetime import datetime, timezone
import json

from app.core.logging import get_logger

logger = get_logger(__name__)


class RAGEventPublisher:
    """
    Публикатор событий статусов RAG документов
    
    Использует ОДИН глобальный канал Redis для всех событий.
    Фильтрация происходит на стороне SSE endpoint по tenant_id и role.
    
    Это предотвращает рост количества каналов и упрощает архитектуру.
    """
    
    # Единый канал для всех RAG событий
    CHANNEL_NAME = "rag:status:updates"
    
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
        
        event = {
            'event_type': 'status_update',
            'document_id': str(doc_id),
            'tenant_id': str(tenant_id),
            'user_id': str(user_id) if user_id else None,
            'stage': stage,
            'status': status,
            'error': error,
            'metrics': metrics or {},
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        try:
            # Публикуем в единый канал
            await self.redis.publish(
                self.CHANNEL_NAME,
                json.dumps(event)
            )
            logger.debug(f"Published status update: {doc_id} - {stage} -> {status}")
        except Exception as e:
            logger.error(f"Failed to publish status update: {e}")
    
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
        
        event = {
            'event_type': 'status_initialized',
            'document_id': str(doc_id),
            'tenant_id': str(tenant_id),
            'user_id': str(user_id) if user_id else None,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        try:
            await self.redis.publish(
                self.CHANNEL_NAME,
                json.dumps(event)
            )
            logger.debug(f"Published status initialized: {doc_id}")
        except Exception as e:
            logger.error(f"Failed to publish status initialized: {e}")
    
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
        
        event = {
            'event_type': 'ingest_started',
            'document_id': str(doc_id),
            'tenant_id': str(tenant_id),
            'user_id': str(user_id) if user_id else None,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        try:
            await self.redis.publish(
                self.CHANNEL_NAME,
                json.dumps(event)
            )
            logger.debug(f"Published ingest started: {doc_id}")
        except Exception as e:
            logger.error(f"Failed to publish ingest started: {e}")
    
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
        
        event = {
            'event_type': 'document_archived' if archived else 'document_unarchived',
            'document_id': str(doc_id),
            'tenant_id': str(tenant_id),
            'archived': archived,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        try:
            await self.redis.publish(
                self.CHANNEL_NAME,
                json.dumps(event)
            )
            logger.debug(f"Published document {'archived' if archived else 'unarchived'}: {doc_id}")
        except Exception as e:
            logger.error(f"Failed to publish document archive event: {e}")


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
    
    async def subscribe(self):
        """Подписаться на канал событий"""
        self.pubsub = self.redis.pubsub()
        await self.pubsub.subscribe(RAGEventPublisher.CHANNEL_NAME)
        logger.info(f"Subscribed to {RAGEventPublisher.CHANNEL_NAME} (tenant={self.tenant_id}, admin={self.is_admin})")
    
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
                
                # Фильтрация по tenant_id
                if not self.is_admin:
                    # Editor видит только события своего тенанта
                    if event.get('tenant_id') != self.tenant_id:
                        continue
                
                yield event
                
            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode event: {e}")
            except Exception as e:
                logger.error(f"Error processing event: {e}")
    
    async def unsubscribe(self):
        """Отписаться от канала"""
        if self.pubsub:
            await self.pubsub.unsubscribe(RAGEventPublisher.CHANNEL_NAME)
            await self.pubsub.close()
            logger.info(f"Unsubscribed from {RAGEventPublisher.CHANNEL_NAME}")
