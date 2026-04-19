"""SummaryStore — persistence for per-chat DialogueSummary.

One row per chat, keyed by `chat_id`. Upsert semantics: the caller
(MemoryWriter) mutates a `SummaryDTO` and asks us to persist it; we
INSERT on first turn, UPDATE thereafter.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import DialogueSummary
from app.runtime.memory.dto import SummaryDTO


class SummaryStore:
    """Repository for the `dialogue_summaries` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load(self, chat_id: UUID) -> Optional[SummaryDTO]:
        """Return the chat's summary or None if the chat has no turns yet."""
        result = await self._session.execute(
            select(DialogueSummary).where(DialogueSummary.chat_id == chat_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            return None
        return SummaryDTO(
            chat_id=row.chat_id,
            goals=list(row.goals or []),
            done=list(row.done or []),
            entities=dict(row.entities or {}),
            open_questions=list(row.open_questions or []),
            raw_tail=row.raw_tail or "",
            last_updated_turn=row.last_updated_turn,
            updated_at=row.updated_at,
        )

    async def save(self, summary: SummaryDTO) -> None:
        """INSERT-or-UPDATE (PostgreSQL ON CONFLICT on the chat_id PK).

        We use PG's native upsert here instead of fetch-then-branch to
        avoid a read + write round trip: MemoryWriter writes once per
        turn and this is on the end-of-turn hot path.
        """
        now = datetime.now(timezone.utc)
        stmt = pg_insert(DialogueSummary).values(
            chat_id=summary.chat_id,
            goals=summary.goals,
            done=summary.done,
            entities=summary.entities,
            open_questions=summary.open_questions,
            raw_tail=summary.raw_tail,
            last_updated_turn=summary.last_updated_turn,
            updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[DialogueSummary.chat_id],
            set_={
                "goals": stmt.excluded.goals,
                "done": stmt.excluded.done,
                "entities": stmt.excluded.entities,
                "open_questions": stmt.excluded.open_questions,
                "raw_tail": stmt.excluded.raw_tail,
                "last_updated_turn": stmt.excluded.last_updated_turn,
                "updated_at": stmt.excluded.updated_at,
            },
        )
        await self._session.execute(stmt)
        await self._session.flush()
