"""Queries for reconciling sandbox companion chat turns."""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.chat_lifecycle import ACTIVE_STATUSES, WAITING_STATUSES
from app.models.chat import Chats
from app.models.chat_turn import ChatTurn
from app.models.sandbox import SandboxRun


class SandboxChatTurnRepository:
    """Persistence queries for sandbox run/chat-turn lifecycle reconciliation."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_turns_with_runs_for_reconciliation(
        self, chat_id: UUID,
    ) -> list[tuple[ChatTurn, Optional[SandboxRun]]]:
        """Lock a chat and its active turns, then read their companion runs.

        SandboxRun rows are intentionally not locked here: terminal run states
        are immutable, and taking locks after ChatTurn would invert runner
        terminal-write lock ordering (SandboxRun then ChatTurn).
        """
        chat = (await self.session.execute(
            select(Chats).where(Chats.id == chat_id).with_for_update()
        )).scalar_one_or_none()
        if chat is None:
            return []

        statuses = (*ACTIVE_STATUSES, *WAITING_STATUSES)
        turns_result = await self.session.execute(
            select(ChatTurn)
            .where(
                ChatTurn.chat_id == chat_id,
                ChatTurn.status.in_(statuses),
                ChatTurn.runtime_run_id.is_not(None),
            )
            .with_for_update()
        )
        turns = turns_result.scalars().all()
        if not turns:
            return []

        runs_result = await self.session.execute(
            select(SandboxRun).where(
                SandboxRun.id.in_([turn.runtime_run_id for turn in turns])
            )
        )
        runs_by_id = {run.id: run for run in runs_result.scalars().all()}
        return [(turn, runs_by_id.get(turn.runtime_run_id)) for turn in turns]
