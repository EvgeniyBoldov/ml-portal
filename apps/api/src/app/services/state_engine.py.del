"""
State Engine - жесткая машина состояний с валидацией переходов
"""
from __future__ import annotations
from typing import Optional, Dict, Any, List
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.logging import get_logger
from app.models.state_engine import StatusHistory, EventOutbox
from app.models.rag import RAGDocument
from app.repositories.factory import AsyncRepositoryFactory

logger = get_logger(__name__)


# Разрешенные переходы статусов
ALLOWED_TRANSITIONS: Dict[str, List[str]] = {
    'uploaded': ['processing', 'queued'],
    'queued': ['processing', 'failed'],
    'processing': ['ready', 'failed', 'archived'],
    'ready': ['archived', 'processing'],  # restart
    'failed': ['processing', 'archived'],  # retry
    'archived': [],  # terminal
}

# Внутренние шаги пайплайна
PIPELINE_STEPS = ['extract', 'normalize', 'split', 'embed', 'commit']


class StateTransitionError(Exception):
    """Invalid state transition"""
    pass


class StateEngine:
    """
    Жесткая машина состояний для управления статусами документов.
    
    Все переходы валидируются, записываются в историю и генерируют события.
    """
    
    def __init__(self, session: AsyncSession, repo_factory: AsyncRepositoryFactory):
        self.session = session
        self.repo_factory = repo_factory
    
    async def transition_status(
        self,
        document_id: UUID,
        to_status: str,
        reason: Optional[str] = None,
        actor: Optional[str] = None,
        emit_event: bool = True
    ) -> bool:
        """
        Перевести документ в новый статус с валидацией.
        
        Args:
            document_id: ID документа
            to_status: Новый статус
            reason: Причина перехода
            actor: Кто инициировал переход (user_id или 'system')
            emit_event: Выпустить событие в outbox
            
        Returns:
            True если переход успешен
            
        Raises:
            StateTransitionError: Невалидный переход
        """
        # Получить текущий документ
        result = await self.session.execute(
            select(RAGDocument).where(RAGDocument.id == document_id)
        )
        document = result.scalar_one_or_none()
        
        if not document:
            raise ValueError(f"Document {document_id} not found")
        
        from_status = document.status
        
        # Валидация перехода
        if from_status == to_status:
            logger.debug(f"Document {document_id} already in status {to_status}")
            return True
        
        allowed = ALLOWED_TRANSITIONS.get(from_status, [])
        if to_status not in allowed:
            raise StateTransitionError(
                f"Invalid transition from {from_status} to {to_status}. "
                f"Allowed: {allowed}"
            )
        
        # Записать в историю
        await self._record_history(
            document_id=document_id,
            tenant_id=document.tenant_id or UUID('00000000-0000-0000-0000-000000000000'),
            from_status=from_status,
            to_status=to_status,
            reason=reason,
            actor=actor or 'system'
        )
        
        # Обновить статус документа
        document.status = to_status
        document.updated_at = datetime.now(timezone.utc)
        
        # Выпустить событие в outbox
        if emit_event:
            await self._emit_event(
                event_type='rag.status',
                payload={
                    'id': str(document_id),
                    'status': to_status,
                    'updated_at': document.updated_at.isoformat(),
                }
            )
        
        logger.info(
            f"Status transition: {document_id} {from_status} → {to_status} "
            f"(reason: {reason}, actor: {actor})"
        )
        
        return True
    
    async def _record_history(
        self,
        document_id: UUID,
        tenant_id: UUID,
        from_status: Optional[str],
        to_status: str,
        reason: Optional[str],
        actor: str
    ) -> None:
        """Записать переход статуса в историю"""
        import uuid as uuid_module
        history = StatusHistory(
            id=uuid_module.uuid4(),
            document_id=document_id,
            tenant_id=tenant_id,
            from_status=from_status,
            to_status=to_status,
            reason=reason,
            actor=actor,
            created_at=datetime.now(timezone.utc)
        )
        self.session.add(history)
    
    async def _emit_event(
        self,
        event_type: str,
        payload: Dict[str, Any]
    ) -> None:
        """
        Выпустить событие в outbox.
        
        seq будет автоматически присвоен PostgreSQL последовательностью.
        """
        # Получить следующий seq из последовательности
        from sqlalchemy import text
        import uuid as uuid_module
        result = await self.session.execute(
            text("SELECT nextval('events_outbox_seq_seq')")
        )
        seq = result.scalar()
        
        event = EventOutbox(
            id=uuid_module.uuid4(),
            seq=seq,
            type=event_type,
            payload_json=payload,
            created_at=datetime.now(timezone.utc)
        )
        self.session.add(event)
        
        logger.debug(f"Event emitted: {event_type} (seq={seq})")
    
    async def emit_embed_progress(
        self,
        document_id: UUID,
        model_alias: str,
        done: int,
        total: int,
        last_error: Optional[str] = None
    ) -> None:
        """Выпустить событие прогресса эмбеддинга"""
        await self._emit_event(
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
        self,
        document_id: UUID,
        tags: List[str]
    ) -> None:
        """Выпустить событие обновления тегов"""
        await self._emit_event(
            event_type='rag.tags.updated',
            payload={
                'id': str(document_id),
                'tags': tags,
                'updated_at': datetime.now(timezone.utc).isoformat(),
            }
        )
    
    async def emit_deleted(
        self,
        document_id: UUID
    ) -> None:
        """Выпустить событие удаления документа"""
        await self._emit_event(
            event_type='rag.deleted',
            payload={
                'id': str(document_id),
                'updated_at': datetime.now(timezone.utc).isoformat(),
            }
        )

