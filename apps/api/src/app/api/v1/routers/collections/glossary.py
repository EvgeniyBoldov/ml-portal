"""Read-only endpoint for the virtual Glossary collection."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_uow, get_current_user
from app.services.glossary_catalog_service import (
    GlossaryCatalogTerm,
    GlossaryCatalogService,
)

router = APIRouter(prefix="/glossary")


class GlossaryTermResponse(BaseModel):
    canonical_term: str
    aliases: list[str] = Field(default_factory=list)
    description: str
    updated_at: datetime
    source_document_id: UUID | None
    source_document_title: str | None
    source_section_ids: list[str] = Field(default_factory=list)


class GlossaryOverviewResponse(BaseModel):
    entries: list[GlossaryTermResponse]
    total: int
    limit: int = 100
    offset: int = 0


def _entry_response(entry: GlossaryCatalogTerm) -> GlossaryTermResponse:
    return GlossaryTermResponse(
        canonical_term=entry.canonical_term,
        aliases=list(entry.aliases),
        description=entry.description,
        updated_at=entry.updated_at,
        source_document_id=entry.source_document_id,
        source_document_title=entry.source_document_title,
        source_section_ids=list(entry.source_section_ids),
    )


@router.get("", response_model=GlossaryOverviewResponse)
async def get_glossary_overview(
    session: AsyncSession = Depends(db_uow),
    _user = Depends(get_current_user),
    query: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    entries = await GlossaryCatalogService(session).list_entries()
    normalized = (query or "").strip().casefold()
    filtered = [entry for entry in entries if (
        (not normalized or normalized in entry.canonical_term.casefold()
         or any(normalized in alias.casefold() for alias in entry.aliases)
         or normalized in (entry.description or "").casefold())
    )]
    total = len(filtered)
    return GlossaryOverviewResponse(
        entries=[_entry_response(entry) for entry in filtered[offset:offset + limit]],
        total=total, limit=limit, offset=offset,
    )
