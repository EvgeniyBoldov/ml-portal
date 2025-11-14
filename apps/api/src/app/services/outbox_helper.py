"""
Helper для публикации событий в outbox в рамках транзакции
"""
from __future__ import annotations
from typing import Dict, Any, Optional
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.state_engine import StateEngine


async def emit_status_change(
    session: AsyncSession,
    repo_factory,
    document_id: UUID,
    new_status: str,
    old_status: Optional[str] = None
) -> None:
    """Выпустить событие rag.status при изменении статуса"""
    state_engine = StateEngine(session, repo_factory)
    await state_engine.transition_status(
        document_id=document_id,
        to_status=new_status,
        reason=f"Status changed from {old_status} to {new_status}",
        actor='system',
        emit_event=True
    )


async def emit_embed_progress(
    session: AsyncSession,
    repo_factory,
    document_id: UUID,
    model_alias: str,
    done: int,
    total: int,
    last_error: Optional[str] = None
) -> None:
    """Выпустить событие rag.embed.progress"""
    state_engine = StateEngine(session, repo_factory)
    await state_engine.emit_embed_progress(
        document_id=document_id,
        model_alias=model_alias,
        done=done,
        total=total,
        last_error=last_error
    )


async def emit_tags_updated(
    session: AsyncSession,
    repo_factory,
    document_id: UUID,
    tags: list[str]
) -> None:
    """Выпустить событие rag.tags.updated"""
    state_engine = StateEngine(session, repo_factory)
    await state_engine.emit_tags_updated(
        document_id=document_id,
        tags=tags
    )


async def emit_deleted(
    session: AsyncSession,
    repo_factory,
    document_id: UUID
) -> None:
    """Выпустить событие rag.deleted"""
    state_engine = StateEngine(session, repo_factory)
    await state_engine.emit_deleted(document_id=document_id)

