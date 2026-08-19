"""Read-only endpoint for the virtual Glossary collection."""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends
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
    scope: str
    updated_at: datetime


class GlossaryOverviewResponse(BaseModel):
    entries: list[GlossaryEntryResponse]
    total: int


def _entry_response(entry: GlossaryCatalogEntry) -> GlossaryEntryResponse:
    return GlossaryEntryResponse(
        canonical_term=entry.canonical_term,
        aliases=list(entry.aliases),
        description=entry.description,
        entity_type=entry.entity_type,
        scope=entry.scope,
        updated_at=entry.updated_at,
    )


@router.get("", response_model=GlossaryOverviewResponse)
async def get_glossary_overview(
    session: AsyncSession = Depends(db_uow),
    user: UserCtx = Depends(get_current_user),
):
    tenant_id = await _resolve_requested_tenant_id(session, user, None)
    entries = await GlossaryCatalogService(session).list_entries(
        user_id=UUID(str(user.id)),
        tenant_id=tenant_id,
    )
    return GlossaryOverviewResponse(
        entries=[_entry_response(entry) for entry in entries],
        total=len(entries),
    )
