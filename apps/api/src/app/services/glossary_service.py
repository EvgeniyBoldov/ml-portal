"""Glossary catalogue operations; matching is deliberately not part of v1."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document_memory_staging import GlossaryMeaning, GlossaryTerm
from app.models.glossary import GlossaryEntry
from app.models.project import Project


class GlossaryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def published_terms_query():
        has_meaning = exists(select(GlossaryMeaning.id).where(GlossaryMeaning.term_id == GlossaryTerm.id))
        has_approved_meaning = exists(select(GlossaryMeaning.id).where(
            GlossaryMeaning.term_id == GlossaryTerm.id,
            GlossaryMeaning.resolution_status == "resolved",
        ))
        has_legacy_entry = exists(select(GlossaryEntry.id).where(
            GlossaryEntry.is_active.is_(True),
            GlossaryEntry.scope.in_(("global", "tenant", "project")),
            func.regexp_replace(func.lower(func.btrim(GlossaryEntry.canonical_term)), r"\s+", " ", "g") == GlossaryTerm.normalized_term,
        ))
        return select(GlossaryTerm).where(or_(~has_meaning, has_approved_meaning, has_legacy_entry))

    async def list_active(self) -> list[dict[str, object]]:
        rows = await self._session.execute(self.published_terms_query().order_by(GlossaryTerm.canonical_term))
        return [
            {
                "id": term.id,
                "canonical_term": term.canonical_term,
                "aliases": list(term.aliases or []),
                "created_at": term.created_at,
                "updated_at": term.updated_at,
            }
            for term in rows.scalars().all()
        ]

    async def list_project_terms(self, *, limit: int | None = None) -> list[dict[str, object]]:
        """Thin glossary projection over the canonical project catalogue."""
        stmt = select(Project).where(Project.is_active.is_(True)).order_by(Project.name)
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = await self._session.execute(stmt)
        return [
            {"id": item.id, "key": item.key, "name": item.name, "aliases": list(item.aliases or [])}
            for item in rows.scalars().all()
        ]

    async def list_confirmed_terms(self, *, tenant_id: UUID | None, limit: int | None = None) -> list[dict[str, object]]:
        """Return lexical matches only; meaning and applicability come from memory."""
        stmt = self.published_terms_query().order_by(GlossaryTerm.canonical_term)
        if limit is not None:
            stmt = stmt.limit(limit)
        rows = await self._session.execute(stmt)
        return [{"id": term.id, "term": term.canonical_term,
                 "aliases": list(term.aliases or [])} for term in rows.scalars().all()]
