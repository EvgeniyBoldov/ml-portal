"""Portal-owned model selection and access boundary for the isolated graph worker."""
from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.embeddings import EmbeddingServiceFactory
from app.core.config import get_settings
from redis.asyncio import Redis
from app.models.model_registry import Model, ModelStatus, ModelType
from app.services.embedding_model_config_service import EmbeddingModelConfigService
from app.services.llm_connection_resolver import RegistryLLMConnectionResolver


class HippoRAGService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _models(self) -> dict[str, Any]:
        llm = await RegistryLLMConnectionResolver().resolve(None)
        model = await self.session.scalar(select(Model).where(
            Model.type == ModelType.EMBEDDING, Model.use_for_long_memory.is_(True),
            Model.enabled.is_(True), Model.status == ModelStatus.AVAILABLE,
            Model.deleted_at.is_(None),
        ).order_by(Model.created_at.asc()).limit(1))
        if model is None:
            raise ValueError("LongMemory embedding model is not configured or unavailable")
        await EmbeddingModelConfigService.ensure_registered(self.session, model.alias)
        adapter = EmbeddingServiceFactory.get_service(model.alias)
        info = await asyncio.to_thread(adapter.get_model_info)
        identity = {
            "llm": llm.model_alias, "llm_provider_model": llm.provider_model_name,
            "llm_url": llm.base_url, "llm_extra": llm.extra_config,
            "embedding": model.alias, "embedding_provider_model": model.provider_model_name,
            "embedding_url": model.base_url, "embedding_revision": (model.extra_config or {}).get("revision"),
            "dimensions": info.dimensions, "embedding_tokens": info.max_tokens,
            "embedding_version": model.model_version or info.version, "embedding_normalized": getattr(model, "vector_normalized", None), "context_tokens": llm.context_window_tokens,
        }
        fingerprint = lambda value: hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()
        extraction_identity = fingerprint({key: value for key, value in identity.items() if key.startswith("llm") or key == "context_tokens"})
        embedding_identity = fingerprint({key: value for key, value in identity.items() if key.startswith("embedding") or key == "dimensions"})
        return {"extraction_identity": extraction_identity, "embedding_identity": embedding_identity, "llm_alias": llm.model_alias, "embedding_alias": model.alias,
                "dimensions": info.dimensions, "embedding_tokens": info.max_tokens,
                "context_tokens": llm.context_window_tokens or 16384,
                "qwen": "qwen" in llm.provider_model_name.casefold(),
                "identity": hashlib.sha256(json.dumps(identity, sort_keys=True, default=str).encode()).hexdigest()}

    async def _call(self, operation: str, payload: dict[str, Any]) -> dict[str, Any]:
        settings = get_settings()
        models = await self._models()
        # The worker receives a short-lived capability, never registry credentials.
        token = secrets.token_urlsafe(32)
        key = f"hipporag:capability:{hashlib.sha256(token.encode()).hexdigest()}"
        # Celery uses asyncio.run per task; a pooled global Redis client would
        # remain bound to the previous task's closed event loop.
        redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            await redis.set(key, json.dumps(models), ex=settings.HIPPO_TIMEOUT_SECONDS + 60)
            async with httpx.AsyncClient(timeout=settings.HIPPO_TIMEOUT_SECONDS) as client:
                result = await client.post(f"{settings.HIPPO_WORKER_URL.rstrip('/')}/portal/{operation}", json={
                    **payload, "models": {**models, "callback_url": settings.HIPPO_CALLBACK_URL, "token": token},
                })
                result.raise_for_status()
                return result.json()
        finally:
            try:
                await redis.delete(key)
            finally:
                await redis.aclose()

    async def extract(self, sections: list[dict[str, Any]]) -> dict[str, Any]:
        return await self._call("extract", {"documents": [
            {"id": str(section["id"]), "content": str(section.get("text") or section.get("content") or ""),
             "metadata": {"section_id": str(section["id"])}}
            for section in sections
        ]})

    async def index_document(self, *, document_id: UUID, text: str, metadata: dict[str, Any]) -> dict[str, Any]:
        return await self.index_documents([
            {"id": str(document_id), "content": text, "metadata": metadata},
        ])

    async def index_documents(self, documents: list[dict[str, Any]]) -> dict[str, Any]:
        return await self._call("corpus/index", {"documents": documents})

    async def reindex_embeddings(self) -> dict[str, Any]:
        return await self._call("corpus/reindex", {})

    async def search_documents(self, query: str, *, limit: int = 8) -> dict[str, Any]:
        """Read the shared native graph; no legacy claims or source ACL queries."""
        return await self._call("corpus/search", {"query": query, "top_k": limit})

    async def index_items(self, item_ids: list[UUID] | None = None) -> int:
        """Precompute native OpenIE/vectors; this does not build an ACL-blind read graph."""
        from app.models.memory import MemoryClaim, MemoryItem
        from app.runtime.memory.read_policy import published_claim
        query = select(MemoryClaim, MemoryItem.subject).join(MemoryItem, MemoryItem.id == MemoryClaim.memory_item_id).where(
            published_claim(), MemoryItem.state.in_(("active", "uncertain")), MemoryItem.lifecycle_status == "active",
        )
        if item_ids is not None:
            query = query.where(MemoryItem.id.in_(item_ids))
        count = 0
        # Bounded batches are independent of the total published corpus size.
        result = await self.session.stream(query.execution_options(yield_per=50))
        async for rows in result.partitions(50):
            documents = [{"id": str(claim.id), "content": f"{subject}\n{claim.content_text}",
                          "metadata": {"memory_item_id": str(claim.memory_item_id)}} for claim, subject in rows]
            await self._call("warm", {"documents": documents})
            count += len(documents)
        return count

    async def search_ids(self, query: str, *, items: list[dict[str, Any]], limit: int = 48) -> list[UUID]:
        if not items or not query.strip():
            return []
        # These are ACL-visible, scope-resolved claims, not the global item winner.
        documents = [{"id": str(item["selected_claim_id"]),
                      "content": f"{item['subject']}\n{item['content_text']}",
                      "metadata": {"memory_item_id": str(item["id"]), "claim_id": item["selected_claim_id"]}}
                     for item in items]
        result = await self._call("search", {"query": query, "documents": documents, "top_k": limit})
        allowed = {str(item["id"]) for item in items}
        ids = [UUID(ref["memory_item_id"]) for hit in result["hits"]
               for ref in hit.get("metadata", {}).get("source_refs", [hit.get("metadata", {})])
               if ref.get("memory_item_id") in allowed]
        return list(dict.fromkeys(ids))
