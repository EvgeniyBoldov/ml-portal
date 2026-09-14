"""Read models for the user-facing glossary catalogue."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.glossary import GlossaryEntry, GlossaryObservation, GlossaryScope, GlossaryStatus


@dataclass(frozen=True)
class GlossaryEntryRecord:
    canonical_term: str
    aliases: tuple[str, ...]
    description: str | None
    entity_type: str
    scope: str
    updated_at: datetime
    # Entity graph metadata is additive for the virtual catalogue.  Keep the
    # old read projection constructible for callers that only need a term.
    entity_id: str | None = None
    project_id: UUID | None = None


class GlossaryCatalogRepository:
    """Read confirmed user, tenant and global terms without ownership leakage."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_visible(self, *, user_id: UUID, tenant_id: UUID) -> list[GlossaryEntryRecord]:
        rows = await self._session.execute(
            select(GlossaryEntry, GlossaryObservation)
            .outerjoin(GlossaryObservation, GlossaryObservation.entry_id == GlossaryEntry.id)
            .where(
                GlossaryEntry.is_active.is_(True),
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
        grouped: dict[UUID, tuple[GlossaryEntry, list[GlossaryObservation]]] = {}
        for entry, claim in rows.all():
            current = grouped.setdefault(entry.id, (entry, []))
            if claim is not None and claim.state == "active":
                current[1].append(claim)
        result: list[GlossaryEntryRecord] = []
        for entry, claims in grouped.values():
            visible = [
                claim for claim in claims
                if claim.visibility_tenant_id is None or claim.visibility_tenant_id == tenant_id
            ]
            if claims and not visible:
                continue
            definitions = {str(claim.definition or "").strip() for claim in visible}
            if len(definitions) > 1:
                continue
            if not visible and entry.status != GlossaryStatus.CONFIRMED.value:
                continue
            winner = visible[0] if visible else None
            result.append(GlossaryEntryRecord(
                canonical_term=entry.canonical_term,
                aliases=tuple(winner.aliases if winner else entry.aliases or ()),
                description=(winner.definition if winner else entry.description),
                entity_type=entry.entity_type,
                entity_id=entry.entity_id,
                project_id=entry.project_id,
                scope=entry.scope,
                updated_at=entry.updated_at,
            ))
        return result
