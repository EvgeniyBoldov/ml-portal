"""Lifecycle reconciliation for companion chat turns created by sandbox runs."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sandbox import SandboxRun
from app.repositories.sandbox_chat_turn_repository import SandboxChatTurnRepository
from app.services.chat_turn_service import ChatTurnService
from app.services.sandbox_service import SandboxService


class SandboxTurnLifecycleService:
    """Keep a sandbox run and its hidden-chat turn in the same lifecycle."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.turns = SandboxChatTurnRepository(session)

    async def reconcile_terminal_turns(self, chat_id: UUID) -> int:
        """Close stale companion turns only when their own run is terminal.

        Locking the chat row serializes this repair with ``start_turn``. A live
        or genuinely paused SandboxRun remains the owner and is left untouched.
        The caller owns the transaction commit.
        """
        turn_runs = await self.turns.list_turns_with_runs_for_reconciliation(chat_id)
        now = datetime.now(timezone.utc)
        reconciled = 0
        for turn, run in turn_runs:
            terminal_status = self._turn_status_for_run(run.status) if run is not None else None
            if terminal_status is None:
                continue
            turn.status = terminal_status
            turn.pause_status = None
            turn.paused_action = None
            turn.paused_context = None
            turn.paused_at = None
            turn.completed_at = run.finished_at or now
            if terminal_status == "failed":
                turn.error_message = run.error or "Sandbox runtime failed"
            elif terminal_status == "cancelled":
                turn.error_message = run.error or "Cancelled by user"
            else:
                turn.error_message = None
            reconciled += 1

        if reconciled:
            await self.session.flush()
        return reconciled

    async def fail_setup(self, *, run_id: UUID, error: str) -> None:
        """Fail the run and any companion turn when setup fails before runner ownership."""
        await SandboxService(self.session).finish_run(
            run_id, "failed", error[:2000] or "Sandbox runtime setup failed",
        )
        turn = await ChatTurnService(self.session).get_by_runtime_run_id(run_id)
        if turn is not None:
            await ChatTurnService(self.session).fail_turn(
                turn.id,
                error_message=error[:2000] or "Sandbox runtime setup failed",
            )

    @staticmethod
    def _turn_status_for_run(run_status: str) -> Optional[str]:
        return {
            "completed": "completed",
            "failed": "failed",
            "cancelled": "cancelled",
        }.get(str(run_status))
