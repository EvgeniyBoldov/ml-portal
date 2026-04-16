from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.chat_turn import ChatTurn

logger = get_logger(__name__)


class ChatTurnService:
    """Lifecycle service for persisted chat turns."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    @staticmethod
    def build_request_hash(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    async def start_turn(
        self,
        *,
        tenant_id: str | uuid.UUID,
        chat_id: str | uuid.UUID,
        user_id: str | uuid.UUID,
        idempotency_key: Optional[str] = None,
        request_hash: Optional[str] = None,
    ) -> ChatTurn:
        turn = ChatTurn(
            tenant_id=uuid.UUID(str(tenant_id)),
            chat_id=uuid.UUID(str(chat_id)),
            user_id=uuid.UUID(str(user_id)),
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            status="started",
        )
        self.session.add(turn)
        await self.session.flush()
        return turn

    async def attach_user_message(self, turn_id: str | uuid.UUID, message_id: str | uuid.UUID) -> Optional[ChatTurn]:
        turn = await self.get_by_id(turn_id)
        if not turn:
            return None
        turn.user_message_id = uuid.UUID(str(message_id))
        await self.session.flush()
        return turn

    async def pause_turn(
        self,
        turn_id: str | uuid.UUID,
        *,
        pause_status: str,
        agent_run_id: Optional[str | uuid.UUID] = None,
        paused_action: Optional[dict] = None,
        paused_context: Optional[dict] = None,
    ) -> Optional[ChatTurn]:
        turn = await self.get_by_id(turn_id)
        if not turn:
            return None
        if agent_run_id:
            turn.agent_run_id = uuid.UUID(str(agent_run_id))
        turn.status = "paused"
        turn.pause_status = pause_status
        turn.paused_action = paused_action
        turn.paused_context = paused_context
        turn.paused_at = datetime.now(timezone.utc)
        await self.session.flush()
        return turn

    async def resume_turn(self, turn_id: str | uuid.UUID) -> Optional[ChatTurn]:
        turn = await self.get_by_id(turn_id)
        if not turn:
            return None
        turn.status = "resumed"
        turn.pause_status = None
        turn.paused_action = None
        turn.paused_context = None
        turn.paused_at = None
        await self.session.flush()
        return turn

    async def cancel_turn(
        self,
        turn_id: str | uuid.UUID,
        *,
        error_message: str,
        agent_run_id: Optional[str | uuid.UUID] = None,
    ) -> Optional[ChatTurn]:
        turn = await self.get_by_id(turn_id)
        if not turn:
            return None
        if agent_run_id:
            turn.agent_run_id = uuid.UUID(str(agent_run_id))
        turn.status = "cancelled"
        turn.error_message = error_message
        turn.completed_at = datetime.now(timezone.utc)
        await self.session.flush()
        return turn

    async def complete_turn(
        self,
        turn_id: str | uuid.UUID,
        *,
        assistant_message_id: Optional[str | uuid.UUID] = None,
        agent_run_id: Optional[str | uuid.UUID] = None,
    ) -> Optional[ChatTurn]:
        turn = await self.get_by_id(turn_id)
        if not turn:
            return None
        if assistant_message_id:
            turn.assistant_message_id = uuid.UUID(str(assistant_message_id))
        if agent_run_id:
            turn.agent_run_id = uuid.UUID(str(agent_run_id))
        turn.status = "completed"
        turn.pause_status = None
        turn.paused_action = None
        turn.paused_context = None
        turn.paused_at = None
        turn.completed_at = datetime.now(timezone.utc)
        await self.session.flush()
        return turn

    async def fail_turn(
        self,
        turn_id: str | uuid.UUID,
        *,
        error_message: str,
        agent_run_id: Optional[str | uuid.UUID] = None,
    ) -> Optional[ChatTurn]:
        turn = await self.get_by_id(turn_id)
        if not turn:
            return None
        if agent_run_id:
            turn.agent_run_id = uuid.UUID(str(agent_run_id))
        turn.status = "failed"
        turn.pause_status = None
        turn.paused_action = None
        turn.paused_context = None
        turn.paused_at = None
        turn.error_message = error_message
        turn.completed_at = datetime.now(timezone.utc)
        await self.session.flush()
        return turn

    async def get_by_id(self, turn_id: str | uuid.UUID) -> Optional[ChatTurn]:
        result = await self.session.execute(select(ChatTurn).where(ChatTurn.id == uuid.UUID(str(turn_id))))
        return result.scalar_one_or_none()

    async def get_by_agent_run_id(self, agent_run_id: str | uuid.UUID) -> Optional[ChatTurn]:
        result = await self.session.execute(
            select(ChatTurn)
            .where(ChatTurn.agent_run_id == uuid.UUID(str(agent_run_id)))
            .order_by(ChatTurn.started_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_latest_by_idempotency_key(
        self,
        *,
        chat_id: str | uuid.UUID,
        user_id: str | uuid.UUID,
        idempotency_key: str,
    ) -> Optional[ChatTurn]:
        result = await self.session.execute(
            select(ChatTurn)
            .where(
                ChatTurn.chat_id == uuid.UUID(str(chat_id)),
                ChatTurn.user_id == uuid.UUID(str(user_id)),
                ChatTurn.idempotency_key == idempotency_key,
            )
            .order_by(ChatTurn.started_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def is_in_flight(
        self,
        *,
        chat_id: str | uuid.UUID,
        user_id: str | uuid.UUID,
        idempotency_key: str,
    ) -> bool:
        turn = await self.get_latest_by_idempotency_key(
            chat_id=chat_id,
            user_id=user_id,
            idempotency_key=idempotency_key,
        )
        return bool(turn and turn.status == "started")

    async def has_payload_mismatch(
        self,
        *,
        chat_id: str | uuid.UUID,
        user_id: str | uuid.UUID,
        idempotency_key: str,
        request_hash: str,
    ) -> bool:
        turn = await self.get_latest_by_idempotency_key(
            chat_id=chat_id,
            user_id=user_id,
            idempotency_key=idempotency_key,
        )
        return bool(turn and turn.request_hash and turn.request_hash != request_hash)
