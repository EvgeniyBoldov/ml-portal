from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.chat_turn import ChatTurn
from app.models.chat import Chats

logger = get_logger(__name__)
CHAT_TURN_LEASE_SECONDS = 15 * 60


class ChatTurnIdempotencyError(RuntimeError):
    def __init__(self, *, conflict: bool) -> None:
        self.conflict = conflict
        super().__init__("idempotency_conflict" if conflict else "idempotency_processing")


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
        chat_id: str | uuid.UUID,
        user_id: str | uuid.UUID,
        tenant_id: str | uuid.UUID | None = None,
        idempotency_key: Optional[str] = None,
        request_hash: Optional[str] = None,
        runtime_run_id: Optional[str | uuid.UUID] = None,
    ) -> ChatTurn:
        if idempotency_key:
            existing = await self.get_latest_by_idempotency_key(
                chat_id=chat_id, user_id=user_id, idempotency_key=idempotency_key,
            )
            if existing is not None:
                await self.session.rollback()
                raise ChatTurnIdempotencyError(
                    conflict=bool(request_hash and existing.request_hash and request_hash != existing.request_hash),
                )
        # Serialize turn creation per chat. A row lock makes the active-turn
        # check atomic across API workers, including paused HITL turns.
        if isinstance(self.session, AsyncSession):
            chat = (await self.session.execute(
                select(Chats).where(Chats.id == uuid.UUID(str(chat_id))).with_for_update()
            )).scalar_one_or_none()
            if chat is not None:
                if idempotency_key:
                    existing = await self.get_latest_by_idempotency_key(
                        chat_id=chat_id, user_id=user_id, idempotency_key=idempotency_key,
                    )
                    if existing is not None:
                        await self.session.rollback()
                        raise ChatTurnIdempotencyError(
                            conflict=bool(request_hash and existing.request_hash and request_hash != existing.request_hash),
                        )
                stale_before = datetime.now(timezone.utc).timestamp() - CHAT_TURN_LEASE_SECONDS
                stale_cutoff = datetime.fromtimestamp(stale_before, timezone.utc)
                stale_turns = await self.session.execute(select(ChatTurn).where(
                    ChatTurn.chat_id == uuid.UUID(str(chat_id)),
                    ChatTurn.status.in_(("started", "resumed")),
                    ChatTurn.started_at < stale_cutoff,
                ).with_for_update())
                for stale_turn in stale_turns.scalars().all():
                    stale_turn.status = "failed"
                    stale_turn.error_message = "runtime_lease_expired"
                    stale_turn.completed_at = datetime.now(timezone.utc)
                active = await self.session.execute(select(ChatTurn.id).where(
                    ChatTurn.chat_id == uuid.UUID(str(chat_id)),
                    or_(ChatTurn.status == "paused", and_(
                        ChatTurn.status.in_(("started", "resumed")),
                        ChatTurn.started_at >= stale_cutoff,
                    )),
                ).limit(1))
                if active.scalar_one_or_none() is not None:
                    raise ChatTurnIdempotencyError(conflict=False)
        turn = ChatTurn(
            chat_id=uuid.UUID(str(chat_id)),
            user_id=uuid.UUID(str(user_id)),
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            runtime_run_id=uuid.UUID(str(runtime_run_id)) if runtime_run_id else None,
            status="started",
        )
        self.session.add(turn)
        try:
            await self.session.flush()
        except IntegrityError:
            if not idempotency_key:
                raise
            await self.session.rollback()
            existing = await self.get_latest_by_idempotency_key(
                chat_id=chat_id, user_id=user_id, idempotency_key=idempotency_key,
            )
            if existing is None:
                raise
            raise ChatTurnIdempotencyError(
                conflict=bool(request_hash and existing.request_hash and request_hash != existing.request_hash),
            ) from None
        return turn

    async def attach_user_message(self, turn_id: str | uuid.UUID, message_id: str | uuid.UUID) -> Optional[ChatTurn]:
        turn = await self.get_by_id(turn_id)
        if not turn:
            return None
        turn.user_message_id = uuid.UUID(str(message_id))
        await self.session.flush()
        return turn

    async def attach_assistant_message(self, turn_id: str | uuid.UUID, message_id: str | uuid.UUID) -> Optional[ChatTurn]:
        turn = await self.get_by_id(turn_id)
        if not turn:
            return None
        turn.assistant_message_id = uuid.UUID(str(message_id))
        await self.session.flush()
        return turn

    async def pause_turn(
        self,
        turn_id: str | uuid.UUID,
        *,
        pause_status: str,
        runtime_run_id: Optional[str | uuid.UUID] = None,
        paused_action: Optional[dict] = None,
        paused_context: Optional[dict] = None,
    ) -> Optional[ChatTurn]:
        turn = await self.get_by_id(turn_id)
        if not turn:
            return None
        if runtime_run_id:
            turn.runtime_run_id = uuid.UUID(str(runtime_run_id))
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
        if turn.status == "paused":
            turn.status = "resumed"
            turn.started_at = datetime.now(timezone.utc)
            turn.pause_status = None
            turn.paused_at = None
        elif turn.status != "resumed":
            return None
        await self.session.flush()
        return turn

    async def cancel_turn(
        self,
        turn_id: str | uuid.UUID,
        *,
        error_message: str,
    ) -> Optional[ChatTurn]:
        turn = await self.get_by_id(turn_id)
        if not turn:
            return None
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
    ) -> Optional[ChatTurn]:
        turn = await self.get_by_id(turn_id)
        if not turn:
            return None
        if assistant_message_id:
            turn.assistant_message_id = uuid.UUID(str(assistant_message_id))
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
    ) -> Optional[ChatTurn]:
        turn = await self.get_by_id(turn_id)
        if not turn:
            return None
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

    async def get_by_runtime_run_id(self, runtime_run_id: str | uuid.UUID) -> Optional[ChatTurn]:
        result = await self.session.execute(
            select(ChatTurn)
            .where(ChatTurn.runtime_run_id == uuid.UUID(str(runtime_run_id)))
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
