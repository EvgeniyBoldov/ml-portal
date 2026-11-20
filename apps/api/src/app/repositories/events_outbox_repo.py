"""
Events Outbox Repository for SSE event streaming
"""
from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.events import EventOutbox
from app.repositories.base import AsyncRepository


class AsyncEventsOutboxRepository(AsyncRepository):
    """Async repository for EventOutbox operations"""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, EventOutbox)
    
