"""Persistence queries for owner-scoped administrative fact management."""
from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Fact, FactStatus


class FactAdminRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active(self, *, owner_type: str, owner_id: UUID) -> list[Fact]:
        result = await self._session.execute(
            select(Fact)
            .where(
                Fact.owner_type == owner_type,
                Fact.owner_id == owner_id,
                Fact.superseded_by.is_(None),
                Fact.status == FactStatus.CONFIRMED.value,
            )
            .order_by(Fact.observed_at.desc())
        )
        return list(result.scalars().all())

    async def get_active(self, *, fact_id: UUID, owner_type: str, owner_id: UUID) -> Fact | None:
        result = await self._session.execute(
            select(Fact).where(
                Fact.id == fact_id,
                Fact.owner_type == owner_type,
                Fact.owner_id == owner_id,
                Fact.superseded_by.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def supersede(self, *, fact_id: UUID, replacement_id: UUID) -> None:
        await self._session.execute(
            update(Fact)
            .where(Fact.id == fact_id, Fact.superseded_by.is_(None))
            .values(superseded_by=replacement_id)
        )

    async def add(self, fact: Fact) -> Fact:
        self._session.add(fact)
        await self._session.flush()
        return fact

