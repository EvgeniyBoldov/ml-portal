"""Read model for the canonical runtime event journal."""
from __future__ import annotations

from collections import deque
from typing import Sequence
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.runtime_observability import RuntimeExecutionEvent


class RuntimeEventJournalService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_run_events(self, run_id: UUID) -> Sequence[RuntimeExecutionEvent]:
        result = await self._session.execute(
            select(RuntimeExecutionEvent)
            .where(RuntimeExecutionEvent.run_id == run_id)
            .order_by(RuntimeExecutionEvent.sequence)
        )
        return result.scalars().all()

    async def count_run_events(self, run_id: UUID) -> int:
        return int(await self._session.scalar(
            select(func.count()).select_from(RuntimeExecutionEvent)
            .where(RuntimeExecutionEvent.run_id == run_id)
        ) or 0)

    async def list_agent_execution_events(self, agent_execution_id: str) -> Sequence[RuntimeExecutionEvent]:
        """Return the closed journal subgraph owned by one agent execution.

        Runtime events form a parent graph rather than a flat list: an LLM
        call can own tool calls and retries.  Filtering only direct children
        loses precisely the detail an operator opens the run for.
        """
        roots = (await self._session.execute(
            select(RuntimeExecutionEvent.run_id)
            .where(
                RuntimeExecutionEvent.entity_type == "agent_execution",
                RuntimeExecutionEvent.entity_id == agent_execution_id,
            )
            .order_by(RuntimeExecutionEvent.sequence)
            .limit(1)
        )).scalars().all()
        if not roots:
            return []
        rows = list(await self.list_run_events(roots[0]))
        owned: set[tuple[str, str]] = {("agent_execution", agent_execution_id)}
        included: set[UUID] = set()
        pending = deque(rows)
        # Parents sometimes appear after children in resumed historical runs;
        # repeatedly scan until no new ownership edge is discovered.
        while pending:
            row = pending.popleft()
            parent = (str(row.parent_entity_type or ""), str(row.parent_entity_id or ""))
            entity = (str(row.entity_type or ""), str(row.entity_id or ""))
            if entity in owned or parent in owned:
                if row.id not in included:
                    included.add(row.id)
                    if entity[0] and entity[1] and entity not in owned:
                        owned.add(entity)
                        pending.extend(rows)
        return [row for row in rows if row.id in included]

    async def list_agent_executions(
        self, *, tenant_id: UUID | None = None, limit: int = 100, offset: int = 0,
    ) -> list[RuntimeExecutionEvent]:
        """One representative (start/error) row per persisted agent run."""
        stmt = (
            select(RuntimeExecutionEvent)
            .where(
                RuntimeExecutionEvent.entity_type == "agent_execution",
                RuntimeExecutionEvent.origin == "chat",
            )
            .order_by(RuntimeExecutionEvent.occurred_at.desc())
        )
        if tenant_id is not None:
            stmt = stmt.where(RuntimeExecutionEvent.tenant_id == tenant_id)
        rows = list((await self._session.execute(stmt)).scalars().all())
        unique: list[RuntimeExecutionEvent] = []
        positions: dict[str, int] = {}
        for row in rows:
            if not row.entity_id:
                continue
            existing = positions.get(row.entity_id)
            if existing is None:
                positions[row.entity_id] = len(unique)
                unique.append(row)
            elif row.event_type == "agent_start":
                # Metadata displayed in the list (agent slug/task title) is
                # canonical on the lifecycle start, not on later snapshots.
                unique[existing] = row
        return unique[offset:offset + max(1, min(limit, 500))]
