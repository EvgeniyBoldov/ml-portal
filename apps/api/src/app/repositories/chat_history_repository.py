from uuid import UUID

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import Chats, ChatMessages


class ChatHistoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def owned_chat(self, chat_id: UUID, owner_id: UUID) -> Chats | None:
        return await self.session.scalar(select(Chats).where(Chats.id == chat_id, Chats.owner_id == owner_id))

    async def page(self, *, chat_id: UUID, before_message_id: UUID | None, limit: int) -> list[ChatMessages]:
        query = select(ChatMessages).where(ChatMessages.chat_id == chat_id, ChatMessages.role.in_(["user", "assistant"]))
        if before_message_id:
            cursor = await self.session.scalar(select(ChatMessages).where(
                ChatMessages.id == before_message_id, ChatMessages.chat_id == chat_id))
            if cursor is None:
                raise ValueError("History cursor is unavailable in this chat")
            query = query.where(tuple_(ChatMessages.created_at, ChatMessages.id) < (cursor.created_at, cursor.id))
        return list((await self.session.scalars(query.order_by(
            ChatMessages.created_at.desc(), ChatMessages.id.desc()).limit(limit))).all())
