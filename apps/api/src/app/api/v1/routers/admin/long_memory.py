"""Admin-only read views for the native HippoRAG LongMemory corpus."""
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.schemas.long_memory_admin import (
    LongMemoryAdminDocumentDetail,
    LongMemoryAdminDocumentPage,
    LongMemorySearchPreviewRequest,
    LongMemorySearchPreviewResponse,
    LongMemoryTriplePage,
)
from app.services.long_memory_admin_service import LongMemoryAdminService

router = APIRouter()


@router.get("/documents", response_model=LongMemoryAdminDocumentPage)
async def list_long_memory_documents(
    query: str | None = Query(default=None, max_length=255),
    scope_key: str | None = Query(default=None, max_length=180),
    status: str | None = Query(default=None, max_length=20),
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
) -> dict:
    return await LongMemoryAdminService(session).list_documents(
        limit=limit, offset=offset, query=query, scope_key=scope_key, status=status,
    )


@router.get("/documents/{document_id}", response_model=LongMemoryAdminDocumentDetail)
async def get_long_memory_document(
    document_id: UUID,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
) -> dict:
    document = await LongMemoryAdminService(session).get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="LongMemory document not found")
    return document


@router.get("/documents/{document_id}/triples", response_model=LongMemoryTriplePage)
async def get_long_memory_document_triples(
    document_id: UUID,
    limit: int = Query(default=50, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
) -> dict:
    try:
        page = await LongMemoryAdminService(session).get_document_triples(
            document_id, limit=limit, offset=offset,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="HippoRAG is unavailable") from exc
    if page is None:
        raise HTTPException(status_code=404, detail="LongMemory triples are unavailable")
    return page


@router.post("/search-preview", response_model=LongMemorySearchPreviewResponse)
async def search_long_memory_preview(
    body: LongMemorySearchPreviewRequest,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
) -> dict:
    return await LongMemoryAdminService(session).search_preview(
        scope_key=body.scope_key, query=body.query, limit=body.limit,
    )
