"""Chat CRUD: list, create, update name, update tags, delete."""
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_current_user
from app.core.security import UserCtx
from app.repositories.factory import AsyncRepositoryFactory, get_async_repository_factory

router = APIRouter()


@router.get("/")
async def list_chats(
    limit: int = Query(100, ge=1, le=1000),
    cursor: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    current_user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory),
):
    """List chats with pagination and search"""
    chats_repo = repo_factory.get_chats_repository()
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
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory),
):
    """Create a new chat"""
    name = body.get("name", "New Chat")
    tags = body.get("tags", [])

    chats_repo = repo_factory.get_chats_repository()
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
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory),
):
    """Update chat name"""
    name = body.get("name", "")
    try:
        chat_uuid = uuid.UUID(chat_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid chat ID")

    chats_repo = repo_factory.get_chats_repository()
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
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory),
):
    """Update chat tags"""
    tags = body.get("tags", [])
    try:
        chat_uuid = uuid.UUID(chat_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid chat ID")

    chats_repo = repo_factory.get_chats_repository()
    chat = await chats_repo.update_chat(chat_uuid, tags=tags)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")

    return {"id": chat_id, "tags": tags}


@router.delete("/{chat_id}")
async def delete_chat(
    chat_id: str,
    current_user: UserCtx = Depends(get_current_user),
    repo_factory: AsyncRepositoryFactory = Depends(get_async_repository_factory),
):
    """Delete a chat"""
    try:
        chat_uuid = uuid.UUID(chat_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid chat ID")

    chats_repo = repo_factory.get_chats_repository()
    success = await chats_repo.delete_chat(chat_uuid)
    if not success:
        raise HTTPException(status_code=404, detail="Chat not found")

    return {"id": chat_id, "deleted": True}
