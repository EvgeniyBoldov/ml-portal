# app/api/routers/chats.py
from __future__ import annotations
from typing import Optional, Dict, Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import db_session, get_current_user
from app.repositories.chats_repo import ChatsRepo

router = APIRouter(prefix="/chats", tags=["chats"])

# ---- serializers to match frontend expectations ----
def _ser_chat(c) -> Dict[str, Any]:
    # Chats model: id, name, owner_id, created_at, updated_at, last_message_at (optional)
    return {
        "id": str(c.id),
        "name": c.name or f"Chat {str(c.id)[:8]}",
    }

@router.get("")
def list_chats(
    limit: int = 50,
    cursor: Optional[str] = None,
    session: Session = Depends(db_session),
    user: Dict[str, Any] = Depends(get_current_user),
):
    repo = ChatsRepo(session)
    # get_current_user returns a dict, so we must index by 'id'
    items = repo.list_chats(user["id"])[:limit]
    return {"items": [_ser_chat(c) for c in items], "next_cursor": None}

@router.post("")
def create_chat(
    payload: Dict[str, Any] | None = None,
    session: Session = Depends(db_session),
    user: Dict[str, Any] = Depends(get_current_user),
):
    repo = ChatsRepo(session)
    name = (payload or {}).get("name")
    chat = repo.create_chat(owner_id=user["id"], name=name)
    return {"chat_id": str(chat.id)}
