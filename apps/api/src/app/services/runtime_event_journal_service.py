"""Read model for the canonical runtime event journal."""
from __future__ import annotations

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
