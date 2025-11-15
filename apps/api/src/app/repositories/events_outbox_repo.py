"""
Events Outbox Repository for SSE event streaming
"""
from __future__ import annotations
from typing import List, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from datetime import datetime, timezone

from app.models.events import EventOutbox
from app.repositories.base import AsyncRepository


class AsyncEventsOutboxRepository(AsyncRepository):
    """Async repository for EventOutbox operations"""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, EventOutbox)
    
    async def get_pending_events(
        self,
        last_seq: Optional[int] = None,
        limit: int = 100
    ) -> List[EventOutbox]:
        """
        Получить неотправленные события (delivered_at IS NULL),
        начиная с last_seq (если указан).
        
        Args:
            last_seq: Последний обработанный seq (для incremental чтения)
            limit: Максимальное количество событий
            
        Returns:
            Список событий, отсортированный по seq
        """
        query = select(EventOutbox).where(
            EventOutbox.delivered_at.is_(None)
        )
        
        if last_seq is not None:
            query = query.where(EventOutbox.seq > last_seq)
        
        query = query.order_by(EventOutbox.seq).limit(limit)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def mark_delivered(
        self,
        event_ids: List[UUID]
    ) -> int:
        """
        Пометить события как доставленные.
        
        Args:
            event_ids: Список ID событий для пометки
            
        Returns:
            Количество обновленных событий
        """
        if not event_ids:
            return 0
        
        result = await self.session.execute(
            update(EventOutbox)
            .where(EventOutbox.id.in_(event_ids))
            .where(EventOutbox.delivered_at.is_(None))
            .values(delivered_at=datetime.now(timezone.utc))
        )
        
        return result.rowcount
    
    async def get_oldest_pending_seq(self) -> Optional[int]:
        """Получить самый старый неотправленный seq (для мониторинга backlog)"""
        result = await self.session.execute(
            select(func.min(EventOutbox.seq))
            .where(EventOutbox.delivered_at.is_(None))
        )
        return result.scalar()
    
    async def get_backlog_count(self) -> int:
        """Получить количество неотправленных событий (для метрик)"""
        result = await self.session.execute(
            select(func.count(EventOutbox.id))
            .where(EventOutbox.delivered_at.is_(None))
        )
        return result.scalar() or 0

