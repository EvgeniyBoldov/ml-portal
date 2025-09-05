from __future__ import annotations
from sqlalchemy.orm import Session
from app.repositories.chats_repo import ChatsRepo

def create_chat(session: Session, owner_id, name: str | None):
    return ChatsRepo(session).create_chat(owner_id, name)

def list_chats(session: Session, owner_id):
    return ChatsRepo(session).list_chats(owner_id)

def post_message(session: Session, chat_id, role: str, content: dict, model: str | None = None):
    repo = ChatsRepo(session)
    chat = repo.get(chat_id)
    if not chat:
        raise ValueError("chat_not_found")
    msg = repo.add_message(chat_id, role, content, model)
    chat.last_message_at = msg.created_at
    return msg

def list_messages(session: Session, chat_id):
    return ChatsRepo(session).list_messages(chat_id)

def delete_chat(session: Session, chat_id):
    repo = ChatsRepo(session)
    chat = repo.get(chat_id)
    if not chat:
        return False
    repo.delete(chat)
    return True
