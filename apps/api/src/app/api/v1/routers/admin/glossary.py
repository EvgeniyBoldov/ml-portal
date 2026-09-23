"""Admin API for scope-free terminology and aliases."""
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.models.document_memory_staging import GlossaryTerm
from app.services.glossary_service import GlossaryService

router = APIRouter(prefix="/glossary")


class GlossaryTermInput(BaseModel):
    canonical_term: str = Field(min_length=1, max_length=255)
    aliases: list[str] = Field(default_factory=list)


class GlossaryTermResponse(GlossaryTermInput):
    id: UUID
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


def _clean_aliases(values: list[str], canonical: str) -> list[str]:
    result: list[str] = []
    seen = {canonical.casefold()}
    for raw in values:
        value = " ".join(raw.split())[:255]
        if value and value.casefold() not in seen:
            result.append(value)
            seen.add(value.casefold())
    return result


@router.get("", response_model=list[GlossaryTermResponse])
async def list_glossary(db: AsyncSession = Depends(db_session), _: UserCtx = Depends(require_admin)):
    return await GlossaryService(db).list_active()


@router.post("", response_model=GlossaryTermResponse, status_code=201)
async def create_glossary_term(
    data: GlossaryTermInput,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    canonical = " ".join(data.canonical_term.split())
    if not canonical:
        raise HTTPException(status_code=422, detail="canonical_term is required")
    term = GlossaryTerm(canonical_term=canonical, normalized_term=canonical.casefold()[:200],
                        aliases=_clean_aliases(data.aliases, canonical))
    db.add(term)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Term already exists") from exc
    await db.refresh(term)
    return term


@router.put("/{term_id}", response_model=GlossaryTermResponse)
async def update_glossary_term(
    term_id: UUID,
    data: GlossaryTermInput,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    term = (await db.execute(select(GlossaryTerm).where(GlossaryTerm.id == term_id))).scalar_one_or_none()
    if term is None:
        raise HTTPException(status_code=404, detail="Term not found")
    canonical = " ".join(data.canonical_term.split())
    if not canonical:
        raise HTTPException(status_code=422, detail="canonical_term is required")
    term.canonical_term = canonical
    term.normalized_term = canonical.casefold()[:200]
    term.aliases = _clean_aliases(data.aliases, canonical)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Term already exists") from exc
    await db.refresh(term)
    return term
