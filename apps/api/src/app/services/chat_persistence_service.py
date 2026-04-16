from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.repositories.chats_repo import AsyncChatMessagesRepository
from app.services.structured_answer_service import StructuredAnswerService

logger = get_logger(__name__)


@dataclass
class PersistedChatMessage:
    message_id: str
    created_at: Optional[str]


class ChatPersistenceService:
    """Service for persisting chat messages and normalizing output."""

    def __init__(self, session: AsyncSession, messages_repo: AsyncChatMessagesRepository) -> None:
        self.session = session
        self.messages_repo = messages_repo
        self.structured_answer_service = StructuredAnswerService()

    async def create_user_message(
        self,
        chat_id: str,
        content: str,
        meta: Optional[Dict[str, Any]] = None,
    ) -> PersistedChatMessage:
        message = await self.messages_repo.create_message(
            chat_id=chat_id,
            role="user",
            content={"text": content},
            meta=meta,
        )
        await self.session.flush()
        await self.session.commit()

        message_id = str(message.id)
        logger.info(f"User message created: {message_id}")
        return PersistedChatMessage(
            message_id=message_id,
            created_at=self.format_datetime(message.created_at),
        )

    async def create_assistant_message(
        self,
        chat_id: str,
        content: str,
        rag_sources: Optional[list[Dict[str, Any]]] = None,
        attachments: Optional[list[Dict[str, Any]]] = None,
    ) -> PersistedChatMessage:
        meta: Dict[str, Any] = {}
        if rag_sources:
            meta["rag_sources"] = rag_sources
        if attachments:
            meta["attachments"] = attachments
        answer_blocks = self.structured_answer_service.build_blocks(
            text=content,
            attachments=attachments,
            rag_sources=rag_sources,
        )
        if answer_blocks:
            meta["answer_contract"] = StructuredAnswerService.CONTRACT_VERSION
            meta["answer_blocks"] = answer_blocks
        meta["grounding"] = self.structured_answer_service.build_grounding(
            rag_sources=rag_sources
        )
        message = await self.messages_repo.create_message(
            chat_id=chat_id,
            role="assistant",
            content={"text": content},
            meta=meta or None,
        )
        await self.session.flush()
        await self.session.commit()

        message_id = str(message.id)
        logger.info(f"Assistant message saved: {message_id}")
        return PersistedChatMessage(
            message_id=message_id,
            created_at=self.format_datetime(message.created_at),
        )

    @staticmethod
    def format_datetime(dt) -> Optional[str]:
        """Normalize datetime to ISO format with Z suffix for consistent API output."""
        if not dt:
            return None
        ts = dt.isoformat()
        if ts.endswith("+00:00"):
            ts = ts[:-6]
        elif ts.endswith("Z"):
            ts = ts[:-1]
        return ts + "Z"
