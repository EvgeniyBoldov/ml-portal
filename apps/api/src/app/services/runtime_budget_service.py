"""Transactional persisted budget ledger."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.runtime_observability import RuntimeBudgetCounter, RuntimeBudgetEntry
from app.runtime.events import RuntimeEvent, RuntimeEventType


@dataclass(frozen=True)
class BudgetDecision:
    allowed: bool
    metric: str
    consumed: int
    limit: Optional[int]
    reason: str


class RuntimeBudgetService:
    def __init__(self, session: AsyncSession, event_sink: Optional[object] = None) -> None:
        self.session = session
        self.event_sink = event_sink

    async def consume(
        self, *, run_id: UUID, owner_type: str, owner_id: str, metric: str,
        amount: int = 1, limit: Optional[int] = None, reason: str = "consume",
        causation_event_id: Optional[UUID] = None,
    ) -> BudgetDecision:
        if amount <= 0:
            return BudgetDecision(True, metric, 0, limit, reason)
        result = await self.session.execute(select(RuntimeBudgetCounter).where(
            RuntimeBudgetCounter.owner_type == owner_type,
            RuntimeBudgetCounter.owner_id == owner_id,
            RuntimeBudgetCounter.metric == metric,
        ).with_for_update())
        counter = result.scalar_one_or_none()
        if counter is None:
            counter = RuntimeBudgetCounter(id=uuid4(), run_id=run_id, owner_type=owner_type,
                                          owner_id=owner_id, metric=metric, consumed=0, limit_value=limit)
            self.session.add(counter)
            await self.session.flush()
        elif limit is not None:
            counter.limit_value = limit
        before = counter.consumed
        after = before + amount
        effective_limit = counter.limit_value
        if effective_limit is not None and after > effective_limit:
            await self._emit(RuntimeEvent(
                RuntimeEventType.BUDGET_REJECTED,
                {"entity_type": owner_type, "entity_id": owner_id,
                 "caused_by_event_id": str(causation_event_id) if causation_event_id else None,
                 "metric": metric, "consumed": before, "limit": effective_limit,
                 "reason": "budget_exceeded"},
            ))
            return BudgetDecision(False, metric, before, effective_limit, "budget_exceeded")
        counter.consumed = after
        self.session.add(RuntimeBudgetEntry(
            id=uuid4(), run_id=run_id, owner_type=owner_type, owner_id=owner_id,
            metric=metric, delta=amount, before_value=before, after_value=after,
            limit_value=effective_limit, reason=reason, causation_event_id=causation_event_id,
        ))
        await self.session.flush()
        await self._emit(RuntimeEvent(
            RuntimeEventType.BUDGET_CONSUMED,
            {"entity_type": owner_type, "entity_id": owner_id,
             "caused_by_event_id": str(causation_event_id) if causation_event_id else None,
             "metric": metric, "delta": amount, "consumed": after,
             "limit": effective_limit, "reason": reason},
        ))
        return BudgetDecision(True, metric, after, effective_limit, reason)

    async def _emit(self, event: RuntimeEvent) -> None:
        if self.event_sink is not None:
            await self.event_sink(event)
