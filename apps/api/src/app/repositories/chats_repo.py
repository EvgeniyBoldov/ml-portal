from __future__ import annotations
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select, desc, asc, or_
from app.models.chat import Chats, ChatMessages

class ChatsRepo:
    def __init__(self, session: Session):
        self.s = session

    # Chats
    def create_chat(self, owner_id, name: str | None, tags: List[str] | None = None) -> Chats:
        chat = Chats(owner_id=owner_id, name=name, tags=tags or [])
        self.s.add(chat)
        self.s.flush()
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

    # Messages
    def add_message(self, chat_id, role: str, content: dict | str, model: str | None = None) -> ChatMessages:
        if isinstance(content, str):
            payload = {"text": content}
        else:
            payload = content
        msg = ChatMessages(chat_id=chat_id, role=role, content=payload, model=model)
        self.s.add(msg)
        self.s.flush()
        return msg

    def list_messages(self, chat_id, cursor: Optional[str] = None, limit: int = 50) -> Tuple[List[ChatMessages], Optional[str]]:
        stmt = select(ChatMessages).where(ChatMessages.chat_id == chat_id).order_by(asc(ChatMessages.created_at), asc(ChatMessages.id)).limit(limit)
        if cursor:
            # cursor = created_at ISO or message id string; we simply skip <= cursor id
            try:
                stmt = stmt.where(ChatMessages.id > cursor)  # naive id cursor
            except Exception:
                pass
        rows = list(self.s.scalars(stmt))
        next_cursor = rows[-1].id.hex if rows else None
        return rows, next_cursor
