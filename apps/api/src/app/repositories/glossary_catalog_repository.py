"""Read models for the user-facing glossary catalogue."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.glossary import GlossaryEntry, GlossaryScope, GlossaryStatus


@dataclass(frozen=True)
class GlossaryEntryRecord:
    canonical_term: str
    aliases: tuple[str, ...]
    description: str | None
    entity_type: str
    scope: str
    updated_at: datetime


class GlossaryCatalogRepository:
    """Read confirmed user, tenant and global terms without ownership leakage."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_visible(self, *, user_id: UUID, tenant_id: UUID) -> list[GlossaryEntryRecord]:
        rows = await self._session.execute(
            select(GlossaryEntry)
            .where(
                GlossaryEntry.is_active.is_(True),
                GlossaryEntry.status == GlossaryStatus.CONFIRMED.value,
                or_(
                    GlossaryEntry.scope == GlossaryScope.GLOBAL.value,
                    and_(
                        GlossaryEntry.scope == GlossaryScope.USER.value,
                        GlossaryEntry.user_id == user_id,
                    ),
                    and_(
                        GlossaryEntry.scope == GlossaryScope.TENANT.value,
                        GlossaryEntry.tenant_id == tenant_id,
                    ),
                ),
            )
            .order_by(GlossaryEntry.canonical_term)
        )
        return [
            GlossaryEntryRecord(
                canonical_term=row.canonical_term,
                aliases=tuple(row.aliases or ()),
                description=row.description,
                entity_type=row.entity_type,
                scope=row.scope,
                updated_at=row.updated_at,
            )
            for row in rows.scalars().all()
        ]
