"""Chat router package — split from monolithic chat.py (751 lines).

Sub-routers:
  chats.py       — CRUD чатов (list, create, update, delete, tags)
  messages.py    — Сообщения + SSE stream + resume run
  attachments.py — Upload, download, policy
  meta.py        — /models, /agents, /chat (direct LLM)
"""
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from .chats import router as chats_router
from .chats import create_chat as create_chat_core
from .chats import list_chats as list_chats_core
from .messages import router as messages_router
from .attachments import router as attachments_router
from .meta import router as meta_router
from .messages import resume_run  # backward-compat for tests/importers
from .messages import ChatStreamService, get_redis, get_llm_client  # patch points in legacy tests
from app.api.deps import db_uow, get_current_user
from app.core.security import UserCtx

router = APIRouter(tags=["chat"])

router.include_router(meta_router)
router.include_router(chats_router)
router.include_router(messages_router)
router.include_router(attachments_router)


@router.get("")
async def list_chats_no_slash(
    limit: int = Query(100, ge=1, le=1000),
    cursor: Optional[str] = Query(None),
    q: Optional[str] = Query(None),
    current_user: UserCtx = Depends(get_current_user),
    session: AsyncSession = Depends(db_uow),
):
    return await list_chats_core(
        limit=limit,
        cursor=cursor,
        q=q,
        current_user=current_user,
        session=session,
    )


@router.post("")
async def create_chat_no_slash(
    body: Dict[str, Any],
    current_user: UserCtx = Depends(get_current_user),
    session: AsyncSession = Depends(db_uow),
):
    return await create_chat_core(
        body=body,
        current_user=current_user,
        session=session,
    )

__all__ = [
    "router",
    "resume_run",
    "ChatStreamService",
    "get_redis",
    "get_llm_client",
]
