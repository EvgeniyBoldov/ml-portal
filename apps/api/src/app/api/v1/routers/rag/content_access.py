"""HTTP mapping for the tenant policy on collection-linked RAG documents."""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import UserCtx
from app.models.rag import RAGDocument
from app.services.collection_content_access_service import CollectionContentAccessService


async def require_document_content_access(
    session: AsyncSession,
    user: UserCtx,
    *,
    document_id: UUID,
    tenant_id: UUID | None,
) -> bool:
    """Deny writes to a linked document unless every collection ACL permits it."""
    access = await CollectionContentAccessService(session).document_write_access(
        user_id=user.id,
        document_id=document_id,
        document_tenant_id=tenant_id,
    )
    if not access.allowed:
        if access.reason == "collection_access_denied":
            raise HTTPException(status_code=404, detail="Document not found")
        if access.reason == "collection_inactive":
            raise HTTPException(status_code=409, detail="Collection is inactive")
        raise HTTPException(status_code=403, detail="Tenant collection editor permission required")
    return access.linked_to_collection


async def require_linked_document_content_access(
    session: AsyncSession,
    user: UserCtx,
    document: RAGDocument,
) -> bool:
    """Return whether the document is collection-linked; deny unauthorized linked writes."""
    return await require_document_content_access(
        session,
        user,
        document_id=document.id,
        tenant_id=document.tenant_id,
    )
