"""User-facing read service for the virtual Glossary collection."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.glossary_catalog_repository import GlossaryCatalogRepository


@dataclass(frozen=True)
class GlossaryCatalogEntry:
    canonical_term: str
    aliases: tuple[str, ...]
    description: str | None
    entity_type: str
    scope: str
    updated_at: datetime


class GlossaryCatalogService:
    """Expose an active glossary projection without changing runtime resolution."""

    def __init__(self, session: AsyncSession) -> None:
        self._repository = GlossaryCatalogRepository(session)

    async def list_entries(self, *, user_id: UUID, tenant_id: UUID) -> list[GlossaryCatalogEntry]:
        rows = await self._repository.list_visible(user_id=user_id, tenant_id=tenant_id)
        return [
            GlossaryCatalogEntry(
                canonical_term=row.canonical_term,
                aliases=row.aliases,
                description=row.description,
                entity_type=row.entity_type,
                scope=row.scope,
                updated_at=row.updated_at,
            )
            for row in rows
        ]
