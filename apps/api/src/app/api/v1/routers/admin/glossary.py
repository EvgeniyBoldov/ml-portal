"""Admin API for canonical terminology and aliases."""
from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.models.glossary import GlossaryEntry, GlossaryObservation, GlossaryScope, GlossaryStatus
from app.services.glossary_service import GlossaryService

router = APIRouter(prefix="/glossary")


class GlossaryEntryInput(BaseModel):
    scope: GlossaryScope = GlossaryScope.GLOBAL
    canonical_term: str = Field(min_length=1, max_length=255)
    aliases: list[str] = Field(default_factory=list)
    entity_type: str = Field(default="term", min_length=1, max_length=64)
    entity_id: str | None = Field(default=None, max_length=255)
    description: str | None = None
    tenant_id: UUID | None = None
    project_id: UUID | None = None

    @model_validator(mode="after")
    def validate_owner(self) -> "GlossaryEntryInput":
        if self.scope == GlossaryScope.TENANT and self.tenant_id is None:
            raise ValueError("tenant_id is required for tenant glossary entries")
        if self.scope == GlossaryScope.PROJECT and self.project_id is None:
            raise ValueError("project_id is required for project glossary entries")
        return self


class GlossaryEntryResponse(GlossaryEntryInput):
    id: UUID
    is_active: bool
    status: str
    support_count: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class GlossaryConflictResolution(BaseModel):
    definition: str = Field(min_length=1, max_length=8000)
    aliases: list[str] = Field(default_factory=list)


@router.get("", response_model=list[GlossaryEntryResponse])
async def list_glossary(db: AsyncSession = Depends(db_session), _: UserCtx = Depends(require_admin)):
    return await GlossaryService(db).list_active()


@router.post("", response_model=GlossaryEntryResponse, status_code=201)
async def create_glossary_entry(
    data: GlossaryEntryInput,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    canonical = data.canonical_term.strip()
    aliases = list(dict.fromkeys(item.strip() for item in data.aliases if item.strip() and item.strip().casefold() != canonical.casefold()))
    if not canonical:
        raise HTTPException(status_code=422, detail="canonical_term is required")
    entry = await GlossaryService(db).create(
        scope=data.scope, canonical_term=canonical, aliases=aliases,
        entity_type=data.entity_type.strip(), entity_id=data.entity_id,
        description=data.description, tenant_id=data.tenant_id, project_id=data.project_id,
    )
    await db.commit()
    await db.refresh(entry)
    return entry


@router.post("/{entry_id}/resolve", response_model=GlossaryEntryResponse)
async def resolve_glossary_conflict(
    entry_id: UUID,
    data: GlossaryConflictResolution,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Publish one explicit administrative definition for a conflicted term."""
    entry = (await db.execute(select(GlossaryEntry).where(GlossaryEntry.id == entry_id))).scalar_one_or_none()
    if entry is None:
        raise HTTPException(status_code=404, detail="Glossary entry not found")
    aliases = list(dict.fromkeys(
        value.strip() for value in data.aliases
        if value.strip() and value.strip().casefold() != entry.canonical_term.casefold()
    ))
    await db.execute(update(GlossaryObservation).where(
        GlossaryObservation.entry_id == entry.id,
        GlossaryObservation.state == "active",
    ).values(state="conflict"))
    db.add(GlossaryObservation(
        entry_id=entry.id, source_type="admin", source_ref=f"admin:{uuid4()}",
        source_label="administrative resolution", definition=data.definition.strip(), aliases=aliases,
    ))
    entry.aliases = aliases
    entry.description = data.definition.strip()
    entry.status = GlossaryStatus.CONFIRMED.value
    entry.is_active = True
    entry.support_count = 1
    await db.commit()
    await db.refresh(entry)
    return entry
