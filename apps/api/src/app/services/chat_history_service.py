from __future__ import annotations

import json
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.repositories.chat_history_repository import ChatHistoryRepository


class ChatHistoryService:
    def __init__(self, session: AsyncSession) -> None:
        self.repository = ChatHistoryRepository(session)

    async def read(self, *, chat_id: str, owner_id: str, before_message_id: UUID | None, limit: int) -> dict:
        chat = await self.repository.owned_chat(UUID(chat_id), UUID(owner_id))
        if chat is None:
            raise ValueError("Chat not found or access denied")
        settings = get_settings()
        limit = min(limit, settings.CHAT_HISTORY_PAGE_LIMIT)
        rows = await self.repository.page(chat_id=chat.id, before_message_id=before_message_id, limit=limit + 1)
        has_more = len(rows) > limit
        rows = rows[:limit]
        messages = []
        for row in reversed(rows):
            content = row.content.get("text", "") if isinstance(row.content, dict) else str(row.content or "")
            if not isinstance(content, str):
                content = json.dumps(content, ensure_ascii=False)
            messages.append({"message_id": str(row.id), "role": row.role,
                "content": content[:settings.CHAT_HISTORY_MESSAGE_MAX_CHARS],
                "truncated": len(content) > settings.CHAT_HISTORY_MESSAGE_MAX_CHARS})
        return {"messages": messages, "has_more": has_more,
                "next_before_message_id": str(rows[-1].id) if rows and has_more else None}
