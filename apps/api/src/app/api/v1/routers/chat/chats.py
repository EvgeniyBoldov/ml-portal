"""Chat CRUD: list, create, update name, update tags, delete."""
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_uow, get_current_user
from app.core.security import UserCtx
from app.core.config import is_local
from app.models.tenant import Tenants
from app.models.tenant import UserTenants
from app.repositories.chats_repo import AsyncChatsRepository

router = APIRouter()


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

    tenant_id = None
    for raw_tid in (current_user.tenant_ids or []):
        try:
            tenant_id = uuid.UUID(str(raw_tid))
            break
        except Exception:
            continue
    if not tenant_id:
        tenant_row = await session.execute(
            select(UserTenants.tenant_id)
            .where(UserTenants.user_id == uuid.UUID(str(current_user.id)))
            .order_by(UserTenants.is_default.desc())
            .limit(1)
        )
        tenant_id = tenant_row.scalar_one_or_none()
    if not tenant_id and is_local():
        fallback = await session.execute(
            select(Tenants.id)
            .where(Tenants.is_active.is_(True))
            .order_by(Tenants.created_at.asc())
            .limit(1)
        )
        tenant_id = fallback.scalar_one_or_none()
    if not tenant_id:
        raise HTTPException(status_code=400, detail="User has no tenant assigned")
    chats_repo = AsyncChatsRepository(session, tenant_id=tenant_id, user_id=uuid.UUID(str(current_user.id)))
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
    chat = await chats_repo.update_chat(chat_uuid, name=name)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    return {
        "id": str(chat.id),
        "name": chat.name,
        "created_at": chat.created_at.isoformat() + "Z" if chat.created_at else None,
        "updated_at": chat.updated_at.isoformat() + "Z" if chat.updated_at else None,
        "tags": chat.tags or [],
    }


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

    chats_repo = AsyncChatsRepository(session, tenant_id=None, user_id=uuid.UUID(str(current_user.id)))
    success = await chats_repo.delete_chat(chat_uuid)
    if not success:
        raise HTTPException(status_code=404, detail="Chat not found")

    return {"id": chat_id, "deleted": True}
