"""Chat CRUD: list, create, update name, update tags, delete."""
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_uow, get_current_user, get_llm_client
from app.core.http.clients import LLMClientProtocol
from app.core.security import UserCtx
from app.models.chat import ChatMessages, Chats
from app.repositories.chats_repo import AsyncChatsRepository
from app.services.chat_title_generator import ChatTitleGenerator
from app.services.chats_service import ChatsService

router = APIRouter()


def _message_text(message: ChatMessages) -> str:
    content = message.content
    return str(content.get("text") or "") if isinstance(content, dict) else str(content or "")


@router.get("/")
async def list_chats(
    limit: int = Query(100, ge=1, le=1000),
    cursor: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    current_user: UserCtx = Depends(get_current_user),
    session: AsyncSession = Depends(db_uow),
):
    """List chats with pagination and search"""
    chats_repo = AsyncChatsRepository(session, tenant_id=None, user_id=uuid.UUID(str(current_user.id)))
    chats = await chats_repo.get_user_chats(user_id=str(current_user.id), limit=limit)

    next_cursor = None
    if len(chats) == limit:
        next_cursor = str(len(chats))

    items = [
        {
            "id": str(chat.id),
            "name": chat.name,
            "created_at": chat.created_at.isoformat() + "Z" if chat.created_at else None,
            "updated_at": chat.updated_at.isoformat() + "Z" if chat.updated_at else None,
            "tags": chat.tags or [],
        }
        for chat in chats
    ]

    return {"items": items, "next_cursor": next_cursor, "has_more": next_cursor is not None}


@router.post("/")
async def create_chat(
    body: Dict[str, Any],
    current_user: UserCtx = Depends(get_current_user),
    session: AsyncSession = Depends(db_uow),
):
    """Create a new chat"""
    name = body.get("name", "New Chat")
    tags = body.get("tags", [])

    chats_repo = AsyncChatsRepository(session, tenant_id=None, user_id=uuid.UUID(str(current_user.id)))
    chat = await chats_repo.create_chat(
        owner_id=uuid.UUID(current_user.id),
        name=name,
        tags=tags,
    )
    return {"chat_id": str(chat.id)}


@router.patch("/{chat_id}")
async def update_chat(
    chat_id: str,
    body: Dict[str, Any],
    current_user: UserCtx = Depends(get_current_user),
    session: AsyncSession = Depends(db_uow),
):
    """Update chat name"""
    name = body.get("name", "")
    try:
        chat_uuid = uuid.UUID(chat_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid chat ID")

    chats_repo = AsyncChatsRepository(session, tenant_id=None, user_id=uuid.UUID(str(current_user.id)))
    chat = await chats_repo.update_chat(chat_uuid, name=name, title_source="manual")
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    return {
        "id": str(chat.id),
        "name": chat.name,
        "created_at": chat.created_at.isoformat() + "Z" if chat.created_at else None,
        "updated_at": chat.updated_at.isoformat() + "Z" if chat.updated_at else None,
        "tags": chat.tags or [],
    }


@router.post("/{chat_id}/title-generation")
async def generate_chat_title(
    chat_id: str,
    current_user: UserCtx = Depends(get_current_user),
    session: AsyncSession = Depends(db_uow),
    llm: LLMClientProtocol = Depends(get_llm_client),
):
    """Generate title metadata separately from the chat response stream."""
    try:
        chat_uuid = uuid.UUID(chat_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid chat ID")

    chat = (await session.execute(select(Chats).where(
        Chats.id == chat_uuid,
        Chats.owner_id == uuid.UUID(str(current_user.id)),
    ))).scalar_one_or_none()
    if chat is None:
        raise HTTPException(status_code=404, detail="Chat not found")
    if chat.title_source != "default":
        return {"title": chat.name, "generated": False}

    first_user = (await session.execute(
        select(ChatMessages)
        .where(ChatMessages.chat_id == chat_uuid, ChatMessages.role == "user")
        .order_by(ChatMessages.created_at.asc())
        .limit(1)
    )).scalar_one_or_none()
    first_assistant = (await session.execute(
        select(ChatMessages)
        .where(ChatMessages.chat_id == chat_uuid, ChatMessages.role == "assistant")
        .order_by(ChatMessages.created_at.asc())
        .limit(1)
    )).scalar_one_or_none()
    if first_user is None or first_assistant is None:
        return {"title": chat.name, "generated": False}

    try:
        title = await ChatTitleGenerator(llm).generate(
            user_message=_message_text(first_user),
            assistant_message=_message_text(first_assistant),
        )
    except Exception:
        # This endpoint is optional UI metadata. A title outage must not turn
        # a completed chat turn into a user-visible error.
        return {"title": chat.name, "generated": False}
    if title is None:
        return {"title": chat.name, "generated": False}

    # A simultaneous manual rename wins: update only while the chat is still
    # in its initial default-title state.
    result = await session.execute(
        update(Chats)
        .where(Chats.id == chat_uuid, Chats.title_source == "default")
        .values(name=title, title_source="auto")
    )
    if not result.rowcount:
        await session.refresh(chat)
        return {"title": chat.name, "generated": False}
    return {"title": title, "generated": True}


@router.put("/{chat_id}/tags")
async def update_chat_tags(
    chat_id: str,
    body: Dict[str, Any],
    current_user: UserCtx = Depends(get_current_user),
    session: AsyncSession = Depends(db_uow),
):
    """Update chat tags"""
    tags = body.get("tags", [])
    try:
        chat_uuid = uuid.UUID(chat_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid chat ID")

    chats_repo = AsyncChatsRepository(session, tenant_id=None, user_id=uuid.UUID(str(current_user.id)))
    chat = await chats_repo.update_chat(chat_uuid, tags=tags)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    return {"id": chat_id, "tags": tags}


@router.delete("/{chat_id}")
async def delete_chat(
    chat_id: str,
    current_user: UserCtx = Depends(get_current_user),
    session: AsyncSession = Depends(db_uow),
):
    """Delete a chat"""
    try:
        chat_uuid = uuid.UUID(chat_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid chat ID")

    chats_service = ChatsService(session)
    success = await chats_service.delete_chat(
        chat_id=chat_uuid,
        owner_id=uuid.UUID(str(current_user.id)),
    )
    if not success:
        raise HTTPException(status_code=404, detail="Chat not found")

    return {"id": chat_id, "deleted": True}
