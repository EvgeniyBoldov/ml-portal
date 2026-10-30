"""Serialize mutations to the JSON metadata shared by RAG and LongMemory."""
from __future__ import annotations

from collections.abc import Callable
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection
from app.models.memory_scope import DocumentMemoryScope
from app.models.rag import RAGDocument
from app.models.rag_ingest import DocumentCollectionMembership, Source
from app.repositories.rag_ingest_repos import AsyncSourceRepository
from app.services.document_artifacts import normalize_document_source_meta, upsert_document_artifact


MetadataMutation = Callable[[dict[str, Any]], dict[str, Any]]


class DocumentSourceMetadataService:
    """Publish a small Source.meta change against the latest committed value.

    The repository acquires locks in the global order RAGDocument -> Source
    and refreshes ORM identities. Callers must finish external I/O first. This
    service flushes but leaves commit/rollback to its transaction owner.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _lock(self, source_id: UUID, tenant_id: UUID) -> tuple[RAGDocument, Source | None] | None:
        return await AsyncSourceRepository(self.session, tenant_id).lock_publication_rows(source_id)

    async def mutate(
        self,
        source_id: UUID,
        tenant_id: UUID,
        mutation: MetadataMutation,
        *,
        expected_long_memory_generation: int | None = None,
    ) -> dict[str, Any] | None:
        locked = await self._lock(source_id, tenant_id)
        if locked is None:
            return None
        document, source = locked
        if source is None:
            return None
        if (expected_long_memory_generation is not None
                and document.long_memory_generation != expected_long_memory_generation):
            return None
        current = normalize_document_source_meta(source.meta)
        source.meta = mutation(current)
        await self.session.flush()
        return source.meta

    async def upsert_artifact(
        self,
        source_id: UUID,
        tenant_id: UUID,
        kind: str,
        artifact: dict[str, Any],
    ) -> dict[str, Any] | None:
        return await self.mutate(
            source_id,
            tenant_id,
            lambda meta: upsert_document_artifact(meta, kind, artifact),
        )

    async def publish_canonical_artifact(
        self,
        source_id: UUID,
        tenant_id: UUID,
        artifact: dict[str, Any],
        canonical_key: str,
    ) -> dict[str, Any] | None:
        locked = await self._lock(source_id, tenant_id)
        if locked is None:
            return None
        document, source = locked
        if source is None:
            return None
        source.meta = upsert_document_artifact(source.meta, "canonical", artifact)
        document.s3_key_processed = canonical_key
        await self.session.flush()
        return source.meta

    async def publish_embedding_artifact(
        self,
        source_id: UUID,
        tenant_id: UUID,
        model_alias: str,
        artifact: dict[str, Any],
    ) -> dict[str, Any] | None:
        def update(meta: dict[str, Any]) -> dict[str, Any]:
            embeddings = dict(meta.get("embedding_artifacts") or {})
            embeddings[model_alias] = artifact
            meta["embedding_artifacts"] = embeddings
            return meta

        return await self.mutate(source_id, tenant_id, update)

    async def publish_long_memory_result(
        self,
        source_id: UUID,
        tenant_id: UUID,
        generation: int,
        record: dict[str, Any],
    ) -> str:
        locked = await self._lock(source_id, tenant_id)
        if locked is None:
            return "missing"
        document, source = locked
        if document.long_memory_generation != generation:
            return "stale"
        if source is None:
            return "missing"
        current = normalize_document_source_meta(source.meta)
        current["hipporag"] = record
        source.meta = current
        await self.session.flush()
        return "published"

    async def set_explicit_memory_policy(
        self,
        source_id: UUID,
        tenant_id: UUID,
        enabled: bool,
    ) -> dict[str, Any] | None:
        def update(meta: dict[str, Any]) -> dict[str, Any]:
            memory = dict(meta.get("memory") or {})
            memory.update(policy="explicit", enabled=enabled)
            meta["memory"] = memory
            return meta

        return await self.mutate(source_id, tenant_id, update)

    async def reconcile_collection_policy(
        self,
        source_id: UUID,
        tenant_id: UUID,
    ) -> tuple[bool, RAGDocument] | None:
        locked = await self._lock(source_id, tenant_id)
        if locked is None:
            return None
        document, source = locked
        if source is None:
            return None
        current = normalize_document_source_meta(source.meta)
        memory = dict(current.get("memory") or {})
        if memory.get("policy") == "explicit":
            return bool(memory.get("enabled")), document

        enabled_membership = await self.session.scalar(
            select(func.count(DocumentCollectionMembership.id))
            .join(Collection, Collection.id == DocumentCollectionMembership.collection_id)
            .where(
                DocumentCollectionMembership.source_id == source_id,
                Collection.memory_enabled.is_(True),
            )
        )
        enabled = int(enabled_membership or 0) > 0
        memory.update(enabled=enabled, policy="collection")
        current["memory"] = memory
        source.meta = current
        await self.session.flush()
        return enabled, document

    async def set_scope_unassigned(
        self,
        source_id: UUID,
        tenant_id: UUID,
        *,
        unassigned: bool,
    ) -> bool:
        def update(meta: dict[str, Any]) -> dict[str, Any]:
            memory = dict(meta.get("memory") or {})
            if unassigned:
                memory["scope_unassigned"] = True
            else:
                memory.pop("scope_unassigned", None)
            meta["memory"] = memory
            return meta

        return await self.mutate(source_id, tenant_id, update) is not None

    async def reconcile_scope_assignment(self, source_id: UUID, tenant_id: UUID) -> bool | None:
        locked = await self._lock(source_id, tenant_id)
        if locked is None:
            return None
        _, source = locked
        if source is None:
            return None
        still_scoped = await self.session.scalar(
            select(func.count(DocumentMemoryScope.document_id)).where(
                DocumentMemoryScope.document_id == source_id,
            )
        )
        unassigned = int(still_scoped or 0) == 0
        current = normalize_document_source_meta(source.meta)
        memory = dict(current.get("memory") or {})
        if unassigned:
            memory["scope_unassigned"] = True
        else:
            memory.pop("scope_unassigned", None)
        current["memory"] = memory
        source.meta = current
        await self.session.flush()
        return unassigned
