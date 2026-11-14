"""Durable operation admission for synchronous runs and leased shadow workers."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.shadow_execution_guard import ShadowExecutionGuard
from app.models.shadow_invocation import ShadowInvocation
from app.services.runtime_execution_guard_service import RuntimeExecutionGuardError, _fingerprint


class ShadowExecutionGuardService:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession], *, run_id: UUID,
                 claim_id: UUID, invocation_id: UUID | None = None) -> None:
        self.session_factory = session_factory
        self.key = invocation_id or run_id
        self.claim_id = claim_id
        self.invocation_id = invocation_id

    async def _check_claim(self, session: AsyncSession) -> None:
        if self.invocation_id is not None:
            row = await session.scalar(select(ShadowInvocation).where(
                ShadowInvocation.id == self.invocation_id).with_for_update())
            if row is None or row.status != "running" or row.claim_id != self.claim_id:
                raise RuntimeExecutionGuardError("execution_guard_stale", "Shadow execution claim is no longer current.")

    async def start(self) -> None:
        async with self.session_factory() as session, session.begin():
            await self._check_claim(session)
            row = await session.get(ShadowExecutionGuard, self.key, with_for_update=True)
            if row is None:
                session.add(ShadowExecutionGuard(id=self.key, claim_id=self.claim_id, active=True, calls={}))
            else:
                row.claim_id, row.active = self.claim_id, True

    async def _current(self, session: AsyncSession) -> ShadowExecutionGuard:
        await self._check_claim(session)
        row = await session.get(ShadowExecutionGuard, self.key, with_for_update=True)
        if row is None or not row.active or row.claim_id != self.claim_id:
            raise RuntimeExecutionGuardError("execution_guard_stale", "Shadow execution is no longer active.")
        return row

    async def admit(self, *, operation: str, target: str, arguments: dict) -> str:
        key = _fingerprint(operation, target, arguments)
        async with self.session_factory() as session, session.begin():
            row = await self._current(session)
            previous = row.calls.get(key)
            if previous is not None:
                code = "duplicate_execution_blocked" if previous.get("status") == "completed" else "tool_outcome_unknown"
                raise RuntimeExecutionGuardError(code, "A matching operation already ran or may have executed; verify its result before retrying.")
            row.calls = {**row.calls, key: {"status": "admitted"}}
        return key

    async def complete(self, key: str, *, success: bool | None = None) -> None:
        async with self.session_factory() as session, session.begin():
            row = await self._current(session)
            if key not in row.calls:
                raise RuntimeExecutionGuardError("execution_guard_fence", "Shadow operation admission was lost.")
            row.calls = {**row.calls, key: {"status": "unknown" if success is None else "completed",
                        "outcome": "unknown" if success is None else "succeeded" if success else "failed"}}

    async def finish(self) -> None:
        async with self.session_factory() as session, session.begin():
            # A superseded worker must never close the newer worker's ledger.
            row = await session.get(ShadowExecutionGuard, self.key, with_for_update=True)
            if row is not None and row.claim_id == self.claim_id:
                row.active = False
