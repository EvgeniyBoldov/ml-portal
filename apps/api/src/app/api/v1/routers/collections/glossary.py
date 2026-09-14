"""Read-only endpoint for the virtual Glossary collection."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_uow, get_current_user
from app.api.v1.routers.collections.crud import _resolve_requested_tenant_id
from app.core.security import UserCtx
from app.services.glossary_catalog_service import (
    GlossaryCatalogEntry,
    GlossaryCatalogService,
)

router = APIRouter(prefix="/glossary")


class GlossaryEntryResponse(BaseModel):
    canonical_term: str
    aliases: list[str] = Field(default_factory=list)
    description: str | None = None
    entity_type: str
    entity_id: str | None = None
    project_id: UUID | None = None
    scope: str
    updated_at: datetime


class GlossaryOverviewResponse(BaseModel):
    entries: list[GlossaryEntryResponse]
    total: int
    limit: int = 100
    offset: int = 0


def _entry_response(entry: GlossaryCatalogEntry) -> GlossaryEntryResponse:
    return GlossaryEntryResponse(
        canonical_term=entry.canonical_term,
        aliases=list(entry.aliases),
        description=entry.description,
        entity_type=entry.entity_type,
        entity_id=entry.entity_id,
        project_id=entry.project_id,
        scope=entry.scope,
        updated_at=entry.updated_at,
    )


@router.get("", response_model=GlossaryOverviewResponse)
async def get_glossary_overview(
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
    query: str | None = Query(default=None, max_length=200),
    scope: str | None = Query(default=None, pattern="^(global|tenant|user)$"),
    entity_type: str | None = Query(default=None, max_length=100),
    project_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    tenant_id = await _resolve_requested_tenant_id(session, user, None)
    entries = await GlossaryCatalogService(session).list_entries(
        user_id=UUID(str(user.id)),
        tenant_id=tenant_id,
    )
    normalized = (query or "").strip().casefold()
    filtered = [entry for entry in entries if (
        (not normalized or normalized in entry.canonical_term.casefold()
         or any(normalized in alias.casefold() for alias in entry.aliases)
         or normalized in (entry.description or "").casefold())
        and (scope is None or entry.scope == scope)
        and (entity_type is None or entry.entity_type == entity_type)
        and (project_id is None or entry.project_id == project_id)
    )]
    total = len(filtered)
    return GlossaryOverviewResponse(
        entries=[_entry_response(entry) for entry in filtered[offset:offset + limit]],
        total=total, limit=limit, offset=offset,
    )
