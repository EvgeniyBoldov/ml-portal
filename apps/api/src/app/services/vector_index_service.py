"""One address resolver for provisioning, writers, readers and migration."""
from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.embeddings import EmbeddingServiceFactory
from app.adapters.interfaces.embeddings import EmbeddingInterface
from app.adapters.impl.qdrant import QdrantVectorStore
from app.models.model_registry import Model, ModelType, ModelStatus
from app.services.embedding_model_config_service import EmbeddingModelConfigService
from app.services.model_capabilities import ModelCapabilities, embedding_fingerprint


@dataclass(frozen=True)
class VectorIndexTarget:
    model_alias: str
    collection_name: str
    dimensions: int
    fingerprint: str
    version: str
    legacy_fingerprint: str | None = None
    embedding_service: EmbeddingInterface | None = field(default=None, compare=False, repr=False)


def physical_index_name(base: str, fingerprint: str) -> str:
    """A default change or alias ordering never changes an encoder's address."""
    namespace = hashlib.sha256(base.encode()).hexdigest()[:16]
    return f"vi_{namespace}_{fingerprint}"


class VectorIndexService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def resolve(self, base: str, model_alias: str) -> VectorIndexTarget:
        model = await self.session.scalar(select(Model).where(
            Model.alias == model_alias, Model.type == ModelType.EMBEDDING,
            Model.enabled.is_(True), Model.status == ModelStatus.AVAILABLE, Model.deleted_at.is_(None)))
        if model is None:
            raise ValueError(f"Embedding model '{model_alias}' is unavailable")
        await EmbeddingModelConfigService.ensure_registered(self.session, model_alias)
        service = EmbeddingServiceFactory.get_service(model_alias)
        info = await asyncio.to_thread(service.get_model_info)
        caps = ModelCapabilities.from_model(model)
        if caps.embedding_dimensions and caps.embedding_dimensions != info.dimensions:
            raise ValueError(f"Embedding dimension disagreement for {model_alias}")
        if caps.model_version and info.version and caps.model_version != info.version:
            raise ValueError(f"Embedding version disagreement for {model_alias}; verify the model")
        caps = caps.model_copy(update={"embedding_dimensions": info.dimensions, "model_version": caps.model_version or info.version or None})
        fingerprint = embedding_fingerprint(model, caps)
        legacy = (model.extra_config or {}).get("legacy_embedding_fingerprint")
        if legacy == embedding_fingerprint(model, caps, include_input_policy=False):
            legacy = fingerprint  # Same weights/configuration, legacy input policy.
        return VectorIndexTarget(model_alias, physical_index_name(base, fingerprint), info.dimensions, fingerprint, caps.model_version or "", legacy, service)

    async def resolve_many(self, base: str, aliases: list[str]) -> list[VectorIndexTarget]:
        return [await self.resolve(base, alias) for alias in dict.fromkeys(aliases)]

    async def search_targets(self, base: str, target: VectorIndexTarget, store: QdrantVectorStore) -> list[tuple[str, dict | None]]:
        """Read canonical and demonstrably compatible legacy points during backfill.

        Legacy named collections are never assigned by dimension alone. Alias
        and recorded encoder version are required in each point's search filter.
        """
        targets: list[tuple[str, dict | None]] = []
        if await store.collection_exists(target.collection_name):
            targets.append((target.collection_name, None))
        if target.version and target.legacy_fingerprint == target.fingerprint:
            for name in dict.fromkeys([base, f"{base}__{target.model_alias}"]):
                if await store.collection_exists(name) and await store.vector_dimension(name) == target.dimensions:
                    targets.append((name, {"must": [("embed_model_alias", target.model_alias), ("version", target.version)]}))
        return targets

    @staticmethod
    async def cache_is_current(target: VectorIndexTarget, cached: dict | None, embeddings_key: str,
                               store: QdrantVectorStore, source_id: str, tenant_id: str) -> bool:
        if not cached or cached.get("embedding_fingerprint") != target.fingerprint or cached.get("embeddings_key") != embeddings_key:
            return False
        if not await store.collection_exists(target.collection_name):
            return False
        count = await store.count_by_filter(target.collection_name, {
            "source_id": source_id, "tenant_id": tenant_id, "embedding_fingerprint": target.fingerprint})
        return count == cached.get("indexed_count")

    @staticmethod
    def merge_filters(*filters: dict | None) -> dict | None:
        must = [condition for item in filters if item for condition in item.get("must", [])]
        return {"must": must} if must else None
