"""User-facing read service for the virtual Glossary collection."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.glossary_catalog_repository import GlossaryCatalogRepository


@dataclass(frozen=True)
class GlossaryCatalogTerm:
    canonical_term: str
    aliases: tuple[str, ...]
    description: str
    updated_at: datetime
    source_document_id: UUID | None
    source_document_title: str | None
    source_section_ids: tuple[str, ...]


class GlossaryCatalogService:
    """Expose an active glossary projection without changing runtime resolution."""

    def __init__(self, session: AsyncSession) -> None:
        self._repository = GlossaryCatalogRepository(session)

    async def list_entries(self) -> list[GlossaryCatalogTerm]:
        rows = await self._repository.list_visible()
        return [
            GlossaryCatalogTerm(
                canonical_term=row.canonical_term,
                aliases=row.aliases,
                description=row.description,
                updated_at=row.updated_at,
                source_document_id=row.source_document_id,
                source_document_title=row.source_document_title,
                source_section_ids=row.source_section_ids,
            )
            for row in rows
        ]
