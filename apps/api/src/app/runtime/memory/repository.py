"""
WorkingMemoryRepository — persistence for WorkingMemory on top of the
`execution_memories` table (existing model `ExecutionMemory`).

We keep the table name unchanged (renaming is risky, migrations were reset).
Extra columns introduced for v3 live next to the legacy columns, which are
still used as primary storage to avoid a destructive migration.

Mapping:
    WorkingMemory.run_id             -> execution_memories.run_id
    WorkingMemory.chat_id/tenant_id  -> chat_id/tenant_id
    WorkingMemory.goal               -> goal
    WorkingMemory.question           -> question
    WorkingMemory.dialogue_summary   -> dialogue_summary
    WorkingMemory.current_phase_id   -> current_phase_id
    WorkingMemory.current_agent_slug -> current_agent_slug
    WorkingMemory.status             -> run_status
    WorkingMemory.final_answer       -> final_answer
    WorkingMemory.final_error        -> final_error
    WorkingMemory.finished_at        -> finished_at
    WorkingMemory.intent             -> intent (added by migration 0006)
    WorkingMemory.used_tool_calls    -> used_tool_calls (0006)
    WorkingMemory.used_wall_time_ms  -> used_wall_time_ms (0006)
    WorkingMemory.recent_messages    -> recent_messages (0006, JSONB)
    Everything else                  -> memory_state JSONB blob under 'v3' key
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.execution_memory import ExecutionMemory
from app.runtime.memory.working_memory import WorkingMemory

logger = get_logger(__name__)


MEMORY_STATE_KEY = "v3"


class WorkingMemoryRepository:
    """CRUD for WorkingMemory. Caller owns the session & commit."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ------------------------------------------------------------------ #
    # Load                                                               #
    # ------------------------------------------------------------------ #

    async def load(self, run_id: UUID) -> Optional[WorkingMemory]:
        row = await self._get_row(run_id)
        if not row:
            return None
        return self._row_to_memory(row)

    async def load_latest_for_chat(self, chat_id: UUID) -> Optional[WorkingMemory]:
        """Return the most recent memory for a chat (paused/completed).
        Triage uses this to detect ongoing runs."""
        stmt = (
            select(ExecutionMemory)
            .where(ExecutionMemory.chat_id == chat_id)
            .order_by(ExecutionMemory.updated_at.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        row = result.scalar_one_or_none()
        return self._row_to_memory(row) if row else None

    async def load_paused_for_chat(self, chat_id: UUID) -> List[WorkingMemory]:
        """All paused runs in a chat (waiting_input / waiting_confirmation)."""
        stmt = (
            select(ExecutionMemory)
            .where(
                ExecutionMemory.chat_id == chat_id,
                ExecutionMemory.run_status.in_(["waiting_input", "waiting_confirmation"]),
            )
            .order_by(ExecutionMemory.updated_at.desc())
        )
        result = await self.session.execute(stmt)
        return [self._row_to_memory(r) for r in result.scalars().all()]

    # ------------------------------------------------------------------ #
    # Save                                                               #
    # ------------------------------------------------------------------ #

    async def save(self, memory: WorkingMemory) -> None:
        """Upsert WorkingMemory. Does NOT commit — caller controls the transaction."""
        row = await self._get_row(memory.run_id)
        if row is None:
            row = ExecutionMemory(run_id=memory.run_id)
            self.session.add(row)

        # Primary columns
        row.chat_id = memory.chat_id
        row.tenant_id = memory.tenant_id
        row.goal = memory.goal or None
        row.question = memory.question or None
        row.dialogue_summary = memory.dialogue_summary
        row.current_phase_id = memory.current_phase_id
        row.current_agent_slug = memory.current_agent_slug
        row.run_status = memory.status
        row.final_answer = memory.final_answer
        row.final_error = memory.final_error
        row.finished_at = memory.finished_at

        # v2 JSONB columns (keep populated for backwards compat / SQL queries)
        row.facts = [f.text for f in memory.facts]
        row.open_questions = list(memory.open_questions)
        row.loop_signatures = list(memory.recent_action_signatures)
        row.agent_results = [r.model_dump(mode="json") for r in memory.agent_results]
        row.step_history = [s.model_dump(mode="json") for s in memory.planner_steps[-20:]]

        # v3-only columns (added by migration 0006)
        self._set_if_attr(row, "intent", memory.intent)
        self._set_if_attr(row, "used_tool_calls", memory.used_tool_calls)
        self._set_if_attr(row, "used_wall_time_ms", memory.used_wall_time_ms)
        self._set_if_attr(
            row,
            "recent_messages",
            [m.model_dump(mode="json") for m in memory.recent_messages],
        )

        # Full snapshot in memory_state under 'v3' key — this is the authoritative
        # source for load(); the columns above are projections for SQL queries.
        state = dict(row.memory_state or {})
        state[MEMORY_STATE_KEY] = memory.model_dump(mode="json")
        row.memory_state = state
        row.updated_at = datetime.now(timezone.utc)

        await self.session.flush()

    # ------------------------------------------------------------------ #
    # Internals                                                          #
    # ------------------------------------------------------------------ #

    async def _get_row(self, run_id: UUID) -> Optional[ExecutionMemory]:
        stmt = select(ExecutionMemory).where(ExecutionMemory.run_id == run_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    @staticmethod
    def _row_to_memory(row: ExecutionMemory) -> WorkingMemory:
        state = (row.memory_state or {}).get(MEMORY_STATE_KEY)
        if isinstance(state, dict):
            try:
                return WorkingMemory.model_validate(state)
            except Exception as exc:  # pragma: no cover - corrupted blob fallback
                logger.warning("WorkingMemory v3 snapshot invalid for run=%s: %s", row.run_id, exc)

        # Legacy fallback: reconstruct from flat columns. Used only for old rows
        # written before v3. New rows always carry the v3 snapshot.
        from app.runtime.memory.working_memory import AgentResult, Fact, PlannerStepRecord

        return WorkingMemory(
            run_id=row.run_id,
            chat_id=row.chat_id,
            tenant_id=row.tenant_id,
            goal=row.goal or "",
            question=row.question or "",
            dialogue_summary=row.dialogue_summary,
            status=row.run_status or "running",
            current_phase_id=row.current_phase_id,
            current_agent_slug=row.current_agent_slug,
            final_answer=row.final_answer,
            final_error=row.final_error,
            finished_at=row.finished_at,
            facts=[Fact(text=str(t), source="legacy") for t in (row.facts or [])],
            open_questions=list(row.open_questions or []),
            recent_action_signatures=list(row.loop_signatures or []),
            agent_results=[
                AgentResult.model_validate(ar)
                for ar in (row.agent_results or [])
                if isinstance(ar, dict)
            ],
            planner_steps=[
                PlannerStepRecord.model_validate(s)
                for s in (row.step_history or [])
                if isinstance(s, dict) and "iteration" in s
            ],
        )

    @staticmethod
    def _set_if_attr(row: ExecutionMemory, attr: str, value) -> None:
        """Assign only if the ORM column exists (pre-migration safety)."""
        if hasattr(row, attr):
            setattr(row, attr, value)
