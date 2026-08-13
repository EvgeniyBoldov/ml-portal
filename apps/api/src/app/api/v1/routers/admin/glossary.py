"""Admin API for canonical terminology and aliases."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.models.glossary import GlossaryScope
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

    class Config:
        from_attributes = True


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
