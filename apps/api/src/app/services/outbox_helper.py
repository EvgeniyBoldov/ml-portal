"""
Helper для публикации событий в outbox в рамках транзакции
"""
from __future__ import annotations
from typing import Dict, Any, Optional
from uuid import UUID, uuid4
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.models.events import EventOutbox
from app.core.logging import get_logger

logger = get_logger(__name__)


async def _emit_event(
    session: AsyncSession,
    event_type: str,
    payload: Dict[str, Any]
) -> None:
    """
    Выпустить событие в outbox.
    
    seq будет автоматически присвоен PostgreSQL последовательностью.
    """
    # Получить следующий seq из последовательности
    result = await session.execute(
        text("SELECT nextval('events_outbox_seq_seq')")
    )
    seq = result.scalar()
    
    event = EventOutbox(
        id=uuid4(),
        seq=seq,
        type=event_type,
        payload_json=payload,
        created_at=datetime.now(timezone.utc)
    )
    session.add(event)
    
    logger.debug(f"Event emitted: {event_type} (seq={seq})")


async def emit_status_change(
    session: AsyncSession,
    repo_factory,
    document_id: UUID,
    new_status: str,
    old_status: Optional[str] = None
) -> None:
    """Выпустить событие rag.status при изменении статуса"""
    await _emit_event(
        session,
        event_type='rag.status',
        payload={
            'id': str(document_id),
            'status': new_status,
            'updated_at': datetime.now(timezone.utc).isoformat(),
        }
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
    await _emit_event(
        session,
        event_type='rag.embed.progress',
        payload={
            'id': str(document_id),
            'model_alias': model_alias,
            'done': done,
            'total': total,
            'last_error': last_error,
            'updated_at': datetime.now(timezone.utc).isoformat(),
        }
    )


async def emit_tags_updated(
    session: AsyncSession,
    repo_factory,
    document_id: UUID,
    tags: list[str]
) -> None:
    """Выпустить событие rag.tags.updated"""
    await _emit_event(
        session,
        event_type='rag.tags.updated',
        payload={
            'id': str(document_id),
            'tags': tags,
            'updated_at': datetime.now(timezone.utc).isoformat(),
        }
    )


async def emit_deleted(
    session: AsyncSession,
    repo_factory,
    document_id: UUID
) -> None:
    """Выпустить событие rag.deleted"""
    await _emit_event(
        session,
        event_type='rag.deleted',
        payload={
            'id': str(document_id),
            'updated_at': datetime.now(timezone.utc).isoformat(),
        }
    )

