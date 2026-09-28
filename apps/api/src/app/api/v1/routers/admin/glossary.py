"""Admin API for scope-free terminology and aliases."""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.models.document_memory_staging import GlossaryTerm
from app.services.glossary_service import GlossaryService

router = APIRouter(prefix="/glossary")


class GlossaryTermResponse(BaseModel):
    id: UUID
    canonical_term: str
    normalized_term: str
    definition: str
    aliases: list[str]
    is_active: bool = True
    approved_candidate_id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GlossaryBulkTermRequest(BaseModel):
    ids: list[UUID] = Field(min_length=1, max_length=200)


@router.get("", response_model=list[GlossaryTermResponse])
async def list_glossary(db: AsyncSession = Depends(db_session), _: UserCtx = Depends(require_admin)):
    return await GlossaryService(db).list_terms()


@router.post("/bulk-deactivate")
async def deactivate_glossary_terms(
    payload: GlossaryBulkTermRequest,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    ids = list(dict.fromkeys(payload.ids))
    found_ids = list((await db.execute(select(GlossaryTerm.id).where(GlossaryTerm.id.in_(ids)))).scalars().all())
    if len(found_ids) != len(ids):
        raise HTTPException(status_code=404, detail="One or more glossary terms were not found")
    active_ids = list((await db.execute(
        select(GlossaryTerm.id).where(GlossaryTerm.id.in_(ids), GlossaryTerm.is_active.is_(True))
    )).scalars().all())
    if active_ids:
        await db.execute(update(GlossaryTerm).where(GlossaryTerm.id.in_(active_ids)).values(is_active=False))
        await db.commit()
    return {"deactivated": len(active_ids)}


@router.post("/bulk-activate")
async def activate_glossary_terms(
    payload: GlossaryBulkTermRequest,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    ids = list(dict.fromkeys(payload.ids))
    found_ids = list((await db.execute(select(GlossaryTerm.id).where(GlossaryTerm.id.in_(ids)))).scalars().all())
    if len(found_ids) != len(ids):
        raise HTTPException(status_code=404, detail="One or more glossary terms were not found")
    eligible_ids = set((await db.execute(
        GlossaryService.published_terms_query(require_active=False)
        .with_only_columns(GlossaryTerm.id).where(GlossaryTerm.id.in_(ids))
    )).scalars().all())
    if set(ids) != eligible_ids:
        raise HTTPException(status_code=409, detail="A term needs an approved global document definition before activation")
    result = await db.execute(
        update(GlossaryTerm).where(GlossaryTerm.id.in_(ids), GlossaryTerm.is_active.is_(False)).values(is_active=True)
    )
    await db.commit()
    return {"activated": result.rowcount or 0}


@router.delete("")
async def delete_glossary_terms(
    payload: GlossaryBulkTermRequest,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    ids = list(dict.fromkeys(payload.ids))
    found_ids = list((await db.execute(select(GlossaryTerm.id).where(GlossaryTerm.id.in_(ids)))).scalars().all())
    if len(found_ids) != len(ids):
        raise HTTPException(status_code=404, detail="One or more glossary terms were not found")
    await db.execute(delete(GlossaryTerm).where(GlossaryTerm.id.in_(ids)))
    await db.commit()
    return {"deleted": len(ids)}
