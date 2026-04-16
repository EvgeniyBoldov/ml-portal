"""
Shared helpers for collection document stream/lifecycle routers.
"""
from __future__ import annotations

import asyncio
from typing import Any
import uuid

from fastapi import HTTPException
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import UserCtx
from app.models.rag_ingest import Source


def _problem(status_code: int, error: str, reason: str, **extra: Any) -> HTTPException:
    detail = {"error": error, "reason": reason}
    detail.update(extra)
    return HTTPException(status_code=status_code, detail=detail)


async def _ensure_worker_ready() -> None:
    from app.celery_app import app as celery_app

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: celery_app.control.ping(timeout=2.0))
    if not result:
        raise _problem(503, "Worker is not available", "worker_unavailable")


async def _resolve_document_collection(
    collection_id: uuid.UUID,
    session: AsyncSession,
    user: UserCtx,
):
    from app.services.collection_service import CollectionService

    svc = CollectionService(session)
    collection = await svc.get_by_id(collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")
    if collection.collection_type != "document":
        raise HTTPException(status_code=400, detail="Not a document collection")

    if user.role != "admin":
        user_tenant_id = user.tenant_ids[0] if user.tenant_ids else None
        if not user_tenant_id or str(collection.tenant_id) != user_tenant_id:
            raise HTTPException(status_code=403, detail="Access denied")

    return collection


async def _document_belongs_to_collection(
    session: AsyncSession,
    collection_id: uuid.UUID,
    doc_id: uuid.UUID,
) -> bool:
    result = await session.execute(
        select(Source.source_id).where(
            Source.source_id == doc_id,
            or_(
                Source.meta["collection"]["id"].astext == str(collection_id),
                Source.meta["collection_id"].astext == str(collection_id),
            ),
        )
    )
    return result.scalar_one_or_none() is not None


async def _resolve_collection_and_doc(
    collection_id: uuid.UUID,
    doc_id: str,
    session: AsyncSession,
    user: UserCtx,
):
    collection = await _resolve_document_collection(collection_id, session, user)
    doc_uuid = uuid.UUID(doc_id)
    belongs = await _document_belongs_to_collection(session, collection_id, doc_uuid)
    if not belongs:
        raise HTTPException(status_code=404, detail="Document not found in collection")

    from app.repositories.factory import AsyncRepositoryFactory

    repo_factory = AsyncRepositoryFactory(session, collection.tenant_id, user.id)
    document = await repo_factory.get_rag_document_by_id(doc_uuid)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    return collection, document, doc_uuid, repo_factory
