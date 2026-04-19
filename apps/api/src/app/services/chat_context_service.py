from __future__ import annotations

from typing import Dict, List, Optional
import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.http.clients import LLMClientProtocol
from app.core.logging import get_logger
from app.repositories.chats_repo import AsyncChatMessagesRepository
from app.services.chat_summary_service import ChatSummaryService

logger = get_logger(__name__)


class ChatContextService:
    """Service for chat context loading and summary maintenance."""

    def __init__(
        self,
        session: AsyncSession,
        llm_client: LLMClientProtocol,
        messages_repo: AsyncChatMessagesRepository,
    ) -> None:
        self.session = session
        self.llm_client = llm_client
        self.messages_repo = messages_repo

    async def load_chat_context(self, chat_id: str | uuid.UUID, limit: int = 20) -> List[Dict[str, str]]:
        """Load recent messages for LLM context (raw, no summary)."""
        messages = await self.messages_repo.get_recent_chat_messages(
            chat_id=str(chat_id),
            limit=limit,
        )

        context: List[Dict[str, str]] = []
        for msg in messages:
            content_text = msg.content
            if isinstance(content_text, dict) and "text" in content_text:
                content_text = content_text["text"]
            elif isinstance(content_text, dict):
                content_text = json.dumps(content_text)

            context.append({
                "role": msg.role,
                "content": str(content_text),
            })
        return context

    async def load_chat_context_with_summary(
        self,
        chat_id: str | uuid.UUID,
        recent_limit: int = 3,
    ) -> List[Dict[str, str]]:
        """Load context using summary + last N raw messages."""
        summary = await self.get_latest_summary_text(chat_id)
        recent = await self.load_chat_context(chat_id, limit=recent_limit)

        context: List[Dict[str, str]] = []
        if summary:
            context.append({
                "role": "system",
                "content": f"Conversation summary so far:\n{summary}",
            })
            logger.info(f"Using summary context ({len(summary)} chars) + {len(recent)} recent messages")
        else:
            recent = await self.load_chat_context(chat_id, limit=20)
            logger.info(f"No summary, using {len(recent)} raw messages as context")

        context.extend(recent)
        return context

    async def get_latest_summary_text(self, chat_id: str | uuid.UUID) -> Optional[str]:
        summary_service = ChatSummaryService(self.session)
        return await summary_service.get_summary_text(uuid.UUID(str(chat_id)))

    async def store_summary(
        self,
        chat_id: uuid.UUID,
        summary: str,
        summary_metadata: dict | None = None,
        tenant_id: uuid.UUID | None = None,
    ) -> None:
        """Store summary for chat."""
        messages = await self.load_chat_context(chat_id, limit=100)
        message_count = len(messages)

        summary_service = ChatSummaryService(self.session)
        await summary_service.create_or_update_summary(
            chat_id=chat_id,
            summary_text=summary,
            message_count=message_count,
            tenant_id=tenant_id,
            summary_metadata=summary_metadata,
        )
        logger.info(f"Stored summary for chat {chat_id}: {summary[:100]}...")
