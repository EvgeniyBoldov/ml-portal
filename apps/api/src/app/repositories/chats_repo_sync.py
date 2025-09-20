from __future__ import annotations
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select, desc, asc, or_
from app.models.chat import Chats, ChatMessages

class ChatsRepoSync:
    def __init__(self, session: Session):
        self.s = session

    # Chats
    def create_chat(self, owner_id, name: str | None, tags: List[str] | None = None) -> Chats:
        chat = Chats(owner_id=owner_id, name=name, tags=tags or [])
        self.s.add(chat)
        self.s.flush()
        self.s.refresh(chat)
        return chat

    def list_chats(self, owner_id, q: Optional[str] = None, limit: int = 100) -> List[Chats]:
        stmt = select(Chats).where(Chats.owner_id == owner_id).order_by(desc(Chats.last_message_at), desc(Chats.created_at)).limit(limit)
        if q:
            pattern = f"%{q.lower()}%"
            stmt = stmt.where(or_(Chats.name.ilike(pattern),))
        return list(self.s.scalars(stmt))

    def get(self, chat_id) -> Optional[Chats]:
        try:
            # Convert string to UUID if needed
            if isinstance(chat_id, str):
                import uuid
                chat_id = uuid.UUID(chat_id)
            return self.s.get(Chats, chat_id)
        except (ValueError, TypeError):
            return None

    def delete(self, chat_id):
        chat = self.get(chat_id)
        if chat:
            self.s.delete(chat)
            self.s.flush()

    def rename_chat(self, chat_id, name: str):
        chat = self.get(chat_id)
        if chat:
            chat.name = name
            self.s.flush()

    def update_chat_tags(self, chat_id, tags: List[str]):
        chat = self.get(chat_id)
        if chat:
            chat.tags = tags
            self.s.flush()

    def add_message(self, chat_id, role: str, content: dict, model: str | None = None, tokens_in: int | None = None, tokens_out: int | None = None, meta: dict | None = None) -> ChatMessages:
        message = ChatMessages(chat_id=chat_id, role=role, content=content, model=model, tokens_in=tokens_in, tokens_out=tokens_out, meta=meta)
        self.s.add(message)
        self.s.flush()
        self.s.refresh(message)
        return message

    def list_messages(self, chat_id, limit: int = 100, cursor: Tuple | None = None, role: Optional[str] = None) -> Tuple[List[ChatMessages], bool, Tuple | None]:
        # Стабильная сортировка: created_at DESC, id DESC
        stmt = select(ChatMessages).where(ChatMessages.chat_id == chat_id)
        if role:
            stmt = stmt.where(ChatMessages.role == role)
        stmt = stmt.order_by(desc(ChatMessages.created_at), desc(ChatMessages.id))
        if cursor:
            try:
                ts, last_id = cursor
                from sqlalchemy import and_, or_
                stmt = stmt.where(
                    or_(
                        ChatMessages.created_at < ts,
                        and_(ChatMessages.created_at == ts, ChatMessages.id < last_id)
                    )
                )
            except Exception:
                pass
        stmt = stmt.limit(limit + 1)
        messages = list(self.s.scalars(stmt))
        has_more = len(messages) > limit
        if has_more:
            messages = messages[:limit]
        next_cursor = (messages[-1].created_at, messages[-1].id) if messages and has_more else None
        return messages, has_more, next_cursor

    def get_message(self, message_id) -> Optional[ChatMessages]:
        return self.s.get(ChatMessages, message_id)

    def delete_message(self, message_id):
        message = self.get_message(message_id)
        if message:
            self.s.delete(message)
            self.s.flush()

    def update_message(self, message_id, **updates):
        message = self.get_message(message_id)
        if message:
            for key, value in updates.items():
                if hasattr(message, key):
                    setattr(message, key, value)
            self.s.flush()

    def search_messages(self, chat_id, query: str, limit: int = 100) -> List[ChatMessages]:
        stmt = select(ChatMessages).where(ChatMessages.chat_id == chat_id)
        if query:
            pattern = f"%{query.lower()}%"
            stmt = stmt.where(ChatMessages.content.ilike(pattern))
        stmt = stmt.order_by(desc(ChatMessages.created_at)).limit(limit)
        return list(self.s.scalars(stmt))

    def get_chat_stats(self, chat_id) -> dict:
        chat = self.get(chat_id)
        if not chat:
            return {}
        
        total_messages = self.s.scalar(select(ChatMessages).where(ChatMessages.chat_id == chat_id))
        return {
            "total_messages": total_messages,
            "created_at": chat.created_at,
            "last_message_at": chat.last_message_at,
            "tags": chat.tags
        }
