from __future__ import annotations
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.chat import Chats, ChatMessages

class ChatsRepo:
    def __init__(self, session: Session):
        self.s = session

    def create_chat(self, owner_id, name: str | None) -> Chats:
        chat = Chats(owner_id=owner_id, name=name)
        self.s.add(chat)
        self.s.flush()
        return chat

    def list_chats(self, owner_id) -> List[Chats]:
        return self.s.execute(select(Chats).where(Chats.owner_id == owner_id).order_by(Chats.updated_at.desc())).scalars().all()

    def get(self, chat_id) -> Optional[Chats]:
        return self.s.get(Chats, chat_id)

    def delete(self, chat: Chats):
        self.s.delete(chat)

    def add_message(self, chat_id, role: str, content: dict, model: str | None = None) -> ChatMessages:
        msg = ChatMessages(chat_id=chat_id, role=role, content=content, model=model)
        self.s.add(msg)
        self.s.flush()
        return msg

    def list_messages(self, chat_id) -> List[ChatMessages]:
        return self.s.execute(select(ChatMessages).where(ChatMessages.chat_id == chat_id).order_by(ChatMessages.created_at.asc())).scalars().all()
