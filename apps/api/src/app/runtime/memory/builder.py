"""MemoryBuilder — read path at turn start.

Composes the turn's `WorkingMemory` by loading the per-chat structured
summary and retrieving the top-K active facts across USER, TENANT,
and (if applicable) CHAT scopes. The pipeline then hands the result
to the planner.

The builder itself is stateless; it just stitches together two stores
plus a couple of defaults. Deliberately no LLM calls here — the goal
is a cheap, deterministic read so that every turn has a predictable
memory context.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.memory import FactScope
from app.runtime.memory.dto import SummaryDTO
from app.runtime.memory.fact_store import FactStore
from app.runtime.memory.summary_store import SummaryStore
from app.runtime.memory.transport import TurnMemory

logger = get_logger(__name__)


DEFAULT_FACT_RETRIEVAL_LIMIT = 20


class MemoryBuilder:
    """Assemble a `WorkingMemory` for the current turn."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        fact_limit: int = DEFAULT_FACT_RETRIEVAL_LIMIT,
    ) -> None:
        self._session = session
        self._fact_store = FactStore(session)
        self._summary_store = SummaryStore(session)
        self._fact_limit = fact_limit

    async def build(
        self,
        *,
        goal: str,
        chat_id: Optional[UUID],
        user_id: Optional[UUID],
        tenant_id: Optional[UUID],
    ) -> TurnMemory:
        summary = await self._load_summary(chat_id)
        facts = await self._fact_store.retrieve(
            scopes=_scopes_for(chat_id=chat_id, user_id=user_id, tenant_id=tenant_id),
            user_id=user_id,
            tenant_id=tenant_id,
            chat_id=chat_id,
            limit=self._fact_limit,
        )

        return TurnMemory(
            chat_id=chat_id,
            user_id=user_id,
            tenant_id=tenant_id,
            turn_number=summary.last_updated_turn + 1,
            goal=goal,
            summary=summary,
            retrieved_facts=facts,
        )

    async def _load_summary(self, chat_id: Optional[UUID]) -> SummaryDTO:
        """Load the chat's summary, or a fresh empty one if absent.

        Non-chat contexts (sandbox with no chat_id) get an in-memory
        empty summary whose chat_id is a throwaway — it is never
        persisted because the sandbox code path skips MemoryWriter.
        """
        if chat_id is None:
            # We still need a SummaryDTO so downstream code can read
            # structured fields uniformly. It just won't round-trip.
            from uuid import uuid4
            return SummaryDTO.empty(uuid4())

        existing = await self._summary_store.load(chat_id)
        if existing is not None:
            return existing
        return SummaryDTO.empty(chat_id)


def _scopes_for(
    *,
    chat_id: Optional[UUID],
    user_id: Optional[UUID],
    tenant_id: Optional[UUID],
):
    """Select which scopes to query given the identifiers we have.

    Running a retrieve on a scope we lack an id for is pointless
    (FactStore.retrieve would just skip it via ownership filters, but
    it would still build the SQL). Being explicit here keeps reads
    minimal.
    """
    scopes = []
    if user_id is not None:
        scopes.append(FactScope.USER)
    if tenant_id is not None:
        scopes.append(FactScope.TENANT)
    if chat_id is not None:
        scopes.append(FactScope.CHAT)
    return scopes
