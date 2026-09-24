"""Company-wide semantic index for document-derived memory."""
from __future__ import annotations

import asyncio
import re
from uuid import uuid4
from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.embeddings import EmbeddingServiceFactory
from app.adapters.impl.qdrant import QdrantVectorStore
from app.core.logging import get_logger
from app.models.memory import MemoryClaim, MemoryItem
from app.models.model_registry import Model, ModelStatus, ModelType
from app.services.embedding_model_config_service import EmbeddingModelConfigService

logger = get_logger(__name__)


class MemorySemanticIndex:
    """Qdrant is derived; PostgreSQL remains the source of truth and ACL."""

    def __init__(self, session: AsyncSession, *, vector_store: QdrantVectorStore | None = None) -> None:
        self.session = session
        self.vector_store = vector_store or QdrantVectorStore()

    async def search_ids(self, query: str, *, limit: int = 40) -> list[UUID]:
        model = await self._global_embedding_model()
        if model is None or not str(query or "").strip():
            return []
        try:
            await EmbeddingModelConfigService.ensure_registered(self.session, model.alias)
            service = EmbeddingServiceFactory.get_service(model.alias)
            vector = await asyncio.to_thread(service.embed_text, query)
            collection = await self._read_collection(model.alias)
            points = await self.vector_store.search(
                collection, vector, top_k=limit,
                filter={"must": {"state": ["active", "uncertain"]}},
            )
            result: list[UUID] = []
            for point in points:
                value = str((point.get("payload") or {}).get("memory_item_id") or point.get("id") or "")
                try:
                    result.append(UUID(value))
                except ValueError:
                    continue
            return list(dict.fromkeys(result))
        except Exception as exc:
            logger.warning("Memory semantic search unavailable: %s", exc)
            return []

    async def index_items(self, items: Sequence[MemoryItem], *, collection: str | None = None) -> int:
        model = await self._global_embedding_model()
        if model is None:
            return 0
        await EmbeddingModelConfigService.ensure_registered(self.session, model.alias)
        service = EmbeddingServiceFactory.get_service(model.alias)
        active = [item for item in items if item.state in {"active", "uncertain"} and item.lifecycle_status == "active"]
        if not active:
            return 0
        claim_rows = (await self.session.execute(select(MemoryClaim).where(
            MemoryClaim.memory_item_id.in_([item.id for item in active]),
            MemoryClaim.state == "active",
            MemoryClaim.lifecycle_status == "active",
        ))).scalars().all()
        texts_by_item: dict[UUID, list[str]] = {}
        for claim in claim_rows:
            texts_by_item.setdefault(claim.memory_item_id, []).append(claim.content_text)
        # The vector index is only a candidate generator.  Include every live
        # claim so a tenant-local wording can retrieve the shared identity;
        # Recall resolves the actual text again from ACL-visible claims.
        indexable = [item for item in active if texts_by_item.get(item.id)]
        if not indexable:
            return 0
        vectors = await asyncio.to_thread(
            service.embed_texts,
            [f"{item.subject}\n" + "\n".join(dict.fromkeys(texts_by_item[item.id]))[:16_000] for item in indexable],
        )
        info = service.get_model_info()
        collection = collection or await self._write_collection(model.alias)
        await self.vector_store.ensure_collection(collection, info.dimensions)
        await self.vector_store.upsert(
            collection, vectors,
            [{"memory_item_id": str(item.id), "scope": item.scope,
              "project_id": str(item.project_id) if item.project_id else None,
              "state": item.state} for item in indexable],
            ids=[str(item.id) for item in indexable],
        )
        return len(indexable)

    async def remove_items(self, item_ids: Sequence[UUID]) -> int:
        """Remove retired truth rows from the derived index immediately."""
        model = await self._global_embedding_model()
        if model is None or not item_ids:
            return 0
        collection = await self._read_collection(model.alias)
        if not await self.vector_store.collection_exists(collection):
            return 0
        await self.vector_store.delete_by_filter(
            collection, {"memory_item_id": [str(item_id) for item_id in item_ids]},
        )
        return len(item_ids)

    async def rebuild(self) -> int:
        """Build a shadow index and atomically switch the read alias."""
        model = await self._global_embedding_model()
        if model is None:
            return 0
        shadow = f"{self.physical_collection_name(model.alias)}__build_{uuid4().hex[:12]}"
        indexed = 0
        cursor: UUID | None = None
        while True:
            stmt = select(MemoryItem).where(MemoryItem.state.in_(("active", "uncertain")), MemoryItem.lifecycle_status == "active")
            if cursor is not None:
                stmt = stmt.where(MemoryItem.id > cursor)
            rows = list((await self.session.execute(
                stmt.order_by(MemoryItem.id).limit(100),
            )).scalars().all())
            if not rows:
                break
            indexed += await self.index_items(rows, collection=shadow)
            cursor = rows[-1].id
        # An empty index is still a valid, fully built replacement.
        if not await self.vector_store.collection_exists(shadow):
            info_model = await self._global_embedding_model()
            if info_model is not None:
                await EmbeddingModelConfigService.ensure_registered(self.session, info_model.alias)
                info = EmbeddingServiceFactory.get_service(info_model.alias).get_model_info()
                await self.vector_store.ensure_collection(shadow, info.dimensions)
        old_target = await self.vector_store.alias_target(self.collection_name(model.alias))
        await self.vector_store.replace_alias(alias=self.collection_name(model.alias), collection=shadow)
        if old_target and old_target != shadow:
            await self.vector_store.delete_collection(old_target)
        legacy = self.physical_collection_name(model.alias)
        if legacy != shadow and legacy != old_target and await self.vector_store.collection_exists(legacy):
            await self.vector_store.delete_collection(legacy)
        return indexed

    async def _read_collection(self, model_alias: str) -> str:
        alias = self.collection_name(model_alias)
        if await self.vector_store.collection_exists(alias):
            return alias
        return self.physical_collection_name(model_alias)

    async def _write_collection(self, model_alias: str) -> str:
        return await self._read_collection(model_alias)

    async def _global_embedding_model(self) -> Model | None:
        return (await self.session.execute(
            select(Model).where(
                Model.type == ModelType.EMBEDDING,
                Model.default_for_type.is_(True), Model.enabled.is_(True),
                Model.status == ModelStatus.AVAILABLE, Model.deleted_at.is_(None),
            ).order_by(Model.created_at.asc()).limit(1)
        )).scalars().first()

    @staticmethod
    def collection_name(model_alias: str) -> str:
        safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(model_alias or "default"))[:70]
        return f"company_memory_active__{safe}"

    @staticmethod
    def physical_collection_name(model_alias: str) -> str:
        safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", str(model_alias or "default"))[:70]
        return f"company_memory__{safe}"
