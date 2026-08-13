"""Glossary catalogue operations; matching is deliberately not part of v1."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.glossary import GlossaryEntry, GlossaryScope
from app.models.project import Project


class GlossaryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active(self) -> list[GlossaryEntry]:
        rows = await self._session.execute(
            select(GlossaryEntry).where(GlossaryEntry.is_active.is_(True)).order_by(GlossaryEntry.canonical_term)
        )
        return list(rows.scalars().all())

    async def list_project_terms(self, *, limit: int) -> list[dict[str, object]]:
        """Thin glossary projection over the canonical project catalogue."""
        rows = await self._session.execute(
            select(Project).where(Project.is_active.is_(True)).order_by(Project.name).limit(limit)
        )
        return [
            {"id": item.id, "key": item.key, "name": item.name, "aliases": list(item.aliases or [])}
            for item in rows.scalars().all()
        ]

    async def create(
        self,
        *,
        scope: GlossaryScope,
        canonical_term: str,
        aliases: list[str],
        entity_type: str,
        entity_id: str | None,
        description: str | None,
        tenant_id: UUID | None,
        project_id: UUID | None,
    ) -> GlossaryEntry:
        entry = GlossaryEntry(
            scope=scope.value,
            canonical_term=canonical_term,
            aliases=aliases,
            entity_type=entity_type,
            entity_id=entity_id,
            description=description,
            tenant_id=tenant_id,
            project_id=project_id,
        )
        self._session.add(entry)
        await self._session.flush()
        return entry
