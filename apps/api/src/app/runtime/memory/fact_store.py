"""FactStore — persistence for typed Facts with supersede semantics.

Boundary
--------
Everything that leaves this module is a `FactDTO` (domain object);
everything that enters is a `FactDTO` too. ORM `Fact` rows are a pure
implementation detail and must not leak upwards to
`MemoryBuilder` / `MemoryWriter`.

Conventions
-----------
* Only `flush()` here; never `commit()`. The caller (service layer)
  decides the transaction boundary — see user rules / backend.md.
* Writes are partitioned into tiny primitives
  (`add`, `mark_superseded`) plus one higher-level orchestrator
  (`upsert_with_supersede`). Tests mock the primitives.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional, Sequence
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.memory import Fact, FactScope, FactSource, FactStatus
from app.runtime.memory.dto import FactDTO


class FactStore:
    """Repository for the `facts` table."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ---------------------------------------------------------- read ---

    async def get_active_by_key(
        self,
        *,
        scope: FactScope,
        subject: str,
        owner_type: str,
        owner_id: UUID,
    ) -> Optional[FactDTO]:
        """Return the single active fact that owns this (scope, subject, owner)
        slot, or None. Uses the `ix_facts_scope_subject_active` partial index.
        """
        stmt = select(Fact).where(
            Fact.scope == scope.value,
            Fact.subject == subject,
            Fact.superseded_by.is_(None),
            Fact.status == FactStatus.CONFIRMED.value,
        )
        stmt = stmt.where(Fact.owner_type == owner_type, Fact.owner_id == owner_id)
        result = await self._session.execute(stmt.limit(1))
        row = result.scalar_one_or_none()
        return _orm_to_dto(row) if row else None

    async def retrieve(
        self,
        *,
        scopes: Sequence[FactScope],
        owner_type: Optional[str] = None,
        owner_id: Optional[UUID] = None,
        subject_prefix: Optional[str] = None,
        sources: Optional[Sequence[FactSource]] = None,
        source_ref_contains: Optional[str] = None,
        limit: int = 20,
    ) -> List[FactDTO]:
        """Return up to `limit` active facts matching the ownership filters,
        ordered by observed_at DESC.

        The first retrieval implementation is deliberately dumb — no keyword
        ranking, no embeddings — because the caller (MemoryBuilder) will do
        goal-aware filtering on top. Keep it O(index lookup).
        """
        if not scopes:
            return []
        scope_values = [s.value for s in scopes]
        stmt = select(Fact).where(
            Fact.scope.in_(scope_values),
            Fact.superseded_by.is_(None),
            Fact.status == FactStatus.CONFIRMED.value,
        )

        if owner_type is None or owner_id is None:
            return []
        stmt = stmt.where(Fact.owner_type == owner_type, Fact.owner_id == owner_id)

        if subject_prefix:
            stmt = stmt.where(Fact.subject.like(f"{subject_prefix}%"))
        if sources:
            stmt = stmt.where(Fact.source.in_([source.value for source in sources]))
        if source_ref_contains:
            stmt = stmt.where(Fact.source_ref.like(f"%{source_ref_contains}%"))

        stmt = stmt.order_by(Fact.observed_at.desc()).limit(limit)
        result = await self._session.execute(stmt)
        return [_orm_to_dto(r) for r in result.scalars().all()]

    async def list_user_visible(
        self,
        *,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0,
    ) -> List[FactDTO]:
        """Paginated read for the future 'my facts' user API."""
        stmt = (
            select(Fact)
            .where(
                Fact.owner_type == "user",
                Fact.owner_id == user_id,
                Fact.superseded_by.is_(None),
                Fact.user_visible.is_(True),
                Fact.status == FactStatus.CONFIRMED.value,
            )
            .order_by(Fact.observed_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self._session.execute(stmt)
        return [_orm_to_dto(r) for r in result.scalars().all()]

    # --------------------------------------------------------- write ---

    async def add(self, dto: FactDTO) -> FactDTO:
        """Insert a new fact row as-is. Returns the DTO (with id)."""
        row = Fact(
            id=dto.id,
            tenant_id=dto.tenant_id,
            project_id=dto.project_id,
            owner_type=dto.owner_type,
            owner_id=dto.owner_id,
            kind=dto.kind,
            entry_metadata=dto.metadata or None,
            scope=dto.scope.value,
            subject=dto.subject,
            value=dto.value,
            normalized_value=" ".join(dto.value.lower().split())[:500],
            confidence=dto.confidence,
            source=dto.source.value,
            source_ref=dto.source_ref,
            observed_at=dto.observed_at,
            superseded_by=dto.superseded_by,
            user_visible=dto.user_visible,
            status=dto.status.value,
            support_count=dto.support_count,
            first_confirmed_at=dto.first_confirmed_at,
            last_confirmed_at=dto.last_confirmed_at,
            revision=dto.revision,
        )
        self._session.add(row)
        await self._session.flush()
        return dto

    async def mark_superseded(
        self, *, old_id: UUID, new_id: UUID
    ) -> None:
        """Soft-delete an old fact by linking it to its replacement."""
        stmt = (
            update(Fact)
            .where(Fact.id == old_id, Fact.superseded_by.is_(None))
            .values(superseded_by=new_id)
        )
        await self._session.execute(stmt)

    async def forget(self, fact_id: UUID) -> None:
        """Tombstone a fact (no replacement). superseded_by = self as
        marker so the active-row partial index excludes it.
        """
        stmt = (
            update(Fact)
            .where(Fact.id == fact_id, Fact.superseded_by.is_(None))
            .values(superseded_by=fact_id)
        )
        await self._session.execute(stmt)

    async def forget_owned(self, *, owner_type: str, owner_id: UUID, fact_ids: Sequence[UUID]) -> int:
        result = await self._session.execute(
            update(Fact).where(
                Fact.id.in_(fact_ids), Fact.owner_type == owner_type,
                Fact.owner_id == owner_id, Fact.user_visible.is_(True),
                Fact.superseded_by.is_(None),
            ).values(superseded_by=Fact.id)
        )
        return int(result.rowcount or 0)

    async def reassign_tenant_context(self, *, from_tenant_id: UUID, to_tenant_id: UUID) -> int:
        result = await self._session.execute(
            update(Fact).where(Fact.tenant_id == from_tenant_id).values(tenant_id=to_tenant_id)
        )
        return int(result.rowcount or 0)

    async def upsert_with_supersede(self, new: FactDTO) -> FactDTO:
        """High-level write: apply a new fact against the current active
        slot.

        Decision table:

            existing row?  |  same value?  |  action
            ---------------+---------------+---------------------------------
            no             |  n/a          |  INSERT new, return it
            yes            |  yes          |  bump confidence/observed_at on
                           |               |  existing, return existing
            yes            |  no           |  INSERT new, mark old superseded,
                           |               |  return new

        "Same value" is a strict string equality after both sides are
        stripped. More sophisticated semantic dedup belongs to the
        FactExtractor, not here.
        """
        existing = await self.get_active_by_key(
            scope=new.scope,
            subject=new.subject,
            owner_type=new.owner_type or "",
            owner_id=new.owner_id or UUID(int=0),
        )

        if existing is None:
            return await self.add(new)

        if _values_equivalent(existing.value, new.value):
            # Refresh observed_at + take the higher confidence; leave id intact.
            await self._session.execute(
                update(Fact)
                .where(Fact.id == existing.id)
                .values(
                    observed_at=new.observed_at,
                    confidence=max(existing.confidence, new.confidence),
                )
            )
            # Return a DTO reflecting the post-update state so callers can
            # report "refreshed vs inserted" via id equality.
            return FactDTO(
                scope=existing.scope,
                subject=existing.subject,
                value=existing.value,
                source=existing.source,
                tenant_id=existing.tenant_id,
                owner_type=existing.owner_type,
                owner_id=existing.owner_id,
                kind=existing.kind,
                metadata=existing.metadata,
                confidence=max(existing.confidence, new.confidence),
                source_ref=existing.source_ref,
                observed_at=new.observed_at,
                id=existing.id,
                superseded_by=None,
                user_visible=existing.user_visible,
            )

        # Contradiction — insert new, mark the old as superseded by the new.
        inserted = await self.add(new)
        await self.mark_superseded(old_id=existing.id, new_id=inserted.id)
        return inserted

    # --------------------------------------------------------- misc ---

# ------------------------------------------------------ ORM → DTO ---


def _orm_to_dto(row: Fact) -> FactDTO:
    return FactDTO(
        scope=FactScope(row.scope),
        subject=row.subject,
        value=row.value,
        source=FactSource(row.source),
        tenant_id=row.tenant_id,
        project_id=row.project_id,
        owner_type=row.owner_type,
        owner_id=row.owner_id,
        kind=row.kind or "fact",
        metadata=dict(row.entry_metadata or {}),
        confidence=row.confidence,
        source_ref=row.source_ref,
        observed_at=row.observed_at,
        id=row.id,
        superseded_by=row.superseded_by,
        user_visible=row.user_visible,
        status=FactStatus(row.status),
        support_count=row.support_count,
        first_confirmed_at=row.first_confirmed_at,
        last_confirmed_at=row.last_confirmed_at,
        revision=row.revision,
    )


def _values_equivalent(a: str, b: str) -> bool:
    return (a or "").strip() == (b or "").strip()
