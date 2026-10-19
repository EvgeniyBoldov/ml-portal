"""Persistence for LongMemory commands and their status projection."""
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.long_memory_document import LongMemoryDocumentOperation
from app.models.rag import RAGDocument
from app.models.rag_ingest import RAGStatus, Source, DocumentCollectionMembership
from app.models.collection import Collection


class LongMemoryDocumentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def lock_document(self, document_id: UUID) -> RAGDocument | None:
        return await self.session.scalar(select(RAGDocument).where(RAGDocument.id == document_id).with_for_update().execution_options(populate_existing=True))

    async def enabled(self, document_id: UUID) -> bool:
        source = await self.session.get(Source, document_id)
        memory = dict((source.meta or {}).get("memory") or {}) if source else {}
        if memory.get("policy") == "explicit":
            return bool(memory.get("enabled"))
        enabled = await self.session.scalar(select(Collection.memory_enabled).join(
            DocumentCollectionMembership, DocumentCollectionMembership.collection_id == Collection.id,
        ).where(DocumentCollectionMembership.source_id == document_id).limit(1))
        return bool(enabled if enabled is not None else memory.get("enabled", False))

    async def latest(self, document_id: UUID) -> LongMemoryDocumentOperation | None:
        return await self.session.scalar(select(LongMemoryDocumentOperation).where(
            LongMemoryDocumentOperation.document_id == document_id,
        ).order_by(LongMemoryDocumentOperation.generation.desc()).limit(1))

    async def recoverable(self, limit: int = 50) -> list[UUID]:
        settings = get_settings()
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=settings.HIPPO_OPERATION_LEASE_SECONDS)
        return list((await self.session.scalars(select(LongMemoryDocumentOperation.id).where(
            LongMemoryDocumentOperation.attempts < settings.HIPPO_OPERATION_MAX_ATTEMPTS,
            or_(LongMemoryDocumentOperation.status.in_(("pending", "failed")),
                (LongMemoryDocumentOperation.status == "running") & (LongMemoryDocumentOperation.updated_at < cutoff)),
        ).order_by(LongMemoryDocumentOperation.created_at).limit(limit))).all())

    async def nodes(self, document_id: UUID) -> list[RAGStatus]:
        return list((await self.session.scalars(select(RAGStatus).where(
            RAGStatus.doc_id == document_id, RAGStatus.node_type == "memory",
            RAGStatus.node_key.in_(("knowledge", "graph")),
        ).order_by(RAGStatus.node_key))).all())
