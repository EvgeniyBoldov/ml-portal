from __future__ import annotations
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select, desc, asc, or_
from sqlalchemy.sql import func
from app.models.chat import Chats, ChatMessages

class ChatsRepo:
    def __init__(self, session: Session):
        self.s = session
    def create_chat(self, owner_id, name: str | None, tags: List[str] | None = None) -> Chats:
        chat = Chats(owner_id=owner_id, name=name, tags=tags or [])
        self.s.add(chat); self.s.flush(); return chat
    def list_chats(self, owner_id, q: Optional[str] = None, limit: int = 100) -> List[Chats]:
        stmt = select(Chats).where(Chats.owner_id == owner_id).order_by(desc(Chats.last_message_at), desc(Chats.created_at)).limit(limit)
        if q:
            pattern = f"%{q.lower()}%"
            from sqlalchemy import or_
            stmt = stmt.where(or_(Chats.name.ilike(pattern),))
        return list(self.s.scalars(stmt))
    def get(self, chat_id) -> Optional[Chats]: return self.s.get(Chats, chat_id)
    def delete(self, chat_id): chat = self.get(chat_id); 
    def rename_chat(self, chat_id, name: str): chat = self.get(chat_id); 
    def update_chat_tags(self, chat_id, tags: List[str]): chat = self.get(chat_id); 
    def add_message(self, chat_id, role: str, content: dict | str, model: str | None = None) -> ChatMessages:
        if isinstance(content, str): payload = {"text": content}
        else: payload = content
        msg = ChatMessages(chat_id=chat_id, role=role, content=payload, model=model)
        self.s.add(msg)
        chat = self.get(chat_id)
        if chat: chat.last_message_at = func.now()
        self.s.flush()
        return msg
    def list_messages(self, chat_id, cursor: Optional[str] = None, limit: int = 50) -> Tuple[List[ChatMessages], Optional[str]]:
        stmt = select(ChatMessages).where(ChatMessages.chat_id == chat_id).order_by(asc(ChatMessages.created_at), asc(ChatMessages.id)).limit(limit)
        if cursor:
            try: stmt = stmt.where(ChatMessages.id > cursor)
            except Exception: pass
        rows = list(self.s.scalars(stmt)); next_cursor = rows[-1].id.hex if rows else None; return rows, next_cursor
