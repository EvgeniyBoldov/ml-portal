"""Service for managing chat conversation summaries."""
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.chat_summary import ChatSummary

logger = get_logger(__name__)


class ChatSummaryService:
    """Service for creating, updating, and retrieving chat summaries."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def get_latest_summary(self, chat_id: UUID) -> Optional[ChatSummary]:
        """Get the latest summary for a chat."""
        result = await self.session.execute(
            select(ChatSummary)
            .where(ChatSummary.chat_id == chat_id)
            .order_by(ChatSummary.updated_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
    
    async def get_summary_text(self, chat_id: UUID) -> Optional[str]:
        """Get just the summary text for a chat."""
        summary = await self.get_latest_summary(chat_id)
        return summary.summary_text if summary else None
    
    async def create_or_update_summary(
        self,
        chat_id: UUID,
        summary_text: str,
        message_count: int,
        last_message_id: Optional[UUID] = None,
        tenant_id: Optional[UUID] = None,
        summary_metadata: Optional[dict] = None,
    ) -> ChatSummary:
        """Create or update summary for a chat."""
        existing = await self.get_latest_summary(chat_id)
        
        if existing:
            existing.summary_text = summary_text
            existing.message_count = message_count
            existing.last_message_id = last_message_id
            existing.summary_metadata = summary_metadata
            existing.updated_at = datetime.now(timezone.utc)
            await self.session.flush()
            return existing
        
        summary = ChatSummary(
            chat_id=chat_id,
            tenant_id=tenant_id,
            summary_text=summary_text,
            message_count=message_count,
            last_message_id=last_message_id,
            summary_metadata=summary_metadata,
        )
        self.session.add(summary)
        await self.session.flush()
        return summary
    
    async def delete_summary(self, chat_id: UUID) -> bool:
        """Delete summary for a chat."""
        result = await self.session.execute(
            select(ChatSummary).where(ChatSummary.chat_id == chat_id)
        )
        summary = result.scalar_one_or_none()
        if summary:
            await self.session.delete(summary)
            await self.session.flush()
            return True
        return False
