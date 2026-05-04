"""
Shared helpers for collection document stream/lifecycle routers.
"""
from __future__ import annotations

import asyncio
from typing import Any
import uuid
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import UserCtx
from app.models.rag_ingest import Source, DocumentCollectionMembership


@dataclass
class DocumentMembership:
    source: Source | None
    in_tenant: bool
    in_collection: bool


async def _safe_revoke(task_id: str) -> None:
    from app.celery_app import app as celery_app

    try:
        await asyncio.wait_for(
            asyncio.to_thread(
                celery_app.control.revoke,
                task_id,
                terminate=True,
                signal="SIGTERM",
            ),
            timeout=1.5,
        )
    except Exception:
        pass


async def _stop_pipeline_and_revoke(status_manager: Any, doc_id: uuid.UUID) -> dict[str, Any]:
    stop_result = await status_manager.stop_ingest(doc_id)
    for task_id in stop_result.get("task_ids", []):
        await _safe_revoke(task_id)
    return stop_result


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

    # Document ingest currently depends on Qdrant for index stage.
    # Fail fast instead of queuing a pipeline that will stall/fail later.
    try:
        from app.adapters.impl.qdrant import QdrantVectorStore

        store = QdrantVectorStore()
        await store._client.get_collections()  # noqa: SLF001
    except Exception as exc:
        raise _problem(
            503,
            "Vector index backend is not available",
            "index_backend_unavailable",
            backend="qdrant",
            details=str(exc),
        ) from exc


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


async def _resolve_document_membership(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    collection_id: uuid.UUID,
    doc_id: uuid.UUID,
) -> DocumentMembership:
    explicit_membership = (
        await session.execute(
            select(DocumentCollectionMembership).where(
                DocumentCollectionMembership.source_id == doc_id,
                DocumentCollectionMembership.tenant_id == tenant_id,
                DocumentCollectionMembership.collection_id == collection_id,
            )
        )
    ).scalar_one_or_none()
    source = (
        await session.execute(
            select(Source).where(
                Source.source_id == doc_id,
                Source.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()

    if explicit_membership is not None:
        return DocumentMembership(source=source, in_tenant=True, in_collection=True)

    if source is None:
        return DocumentMembership(source=None, in_tenant=False, in_collection=False)
    return DocumentMembership(source=source, in_tenant=True, in_collection=False)


async def _resolve_collection_and_doc(
    collection_id: uuid.UUID,
    doc_id: str,
    session: AsyncSession,
    user: UserCtx,
):
    collection = await _resolve_document_collection(collection_id, session, user)
    doc_uuid = uuid.UUID(doc_id)
    membership = await _resolve_document_membership(
        session=session,
        tenant_id=collection.tenant_id,
        collection_id=collection_id,
        doc_id=doc_uuid,
    )
    if not membership.in_collection:
        raise HTTPException(status_code=404, detail="Document not found in collection")

    from app.repositories.factory import AsyncRepositoryFactory

    repo_factory = AsyncRepositoryFactory(session, collection.tenant_id, user.id)
    document = await repo_factory.get_rag_document_by_id(doc_uuid)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    return collection, document, doc_uuid, repo_factory


async def _resolve_collection_and_doc_with_membership(
    collection_id: uuid.UUID,
    doc_id: str,
    session: AsyncSession,
    user: UserCtx,
):
    collection = await _resolve_document_collection(collection_id, session, user)
    doc_uuid = uuid.UUID(doc_id)
    membership = await _resolve_document_membership(
        session=session,
        tenant_id=collection.tenant_id,
        collection_id=collection_id,
        doc_id=doc_uuid,
    )
    if not membership.in_collection:
        raise HTTPException(status_code=404, detail="Document not found in collection")

    from app.repositories.factory import AsyncRepositoryFactory

    repo_factory = AsyncRepositoryFactory(session, collection.tenant_id, user.id)
    document = await repo_factory.get_rag_document_by_id(doc_uuid)
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")

    return collection, document, doc_uuid, repo_factory, membership
