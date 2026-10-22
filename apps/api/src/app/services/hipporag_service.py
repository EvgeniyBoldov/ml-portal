"""Portal-owned model selection and access boundary for the isolated graph worker."""
from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
from typing import Any, Awaitable, Callable
from time import monotonic
from uuid import UUID

import httpx
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.embeddings import EmbeddingServiceFactory
from app.core.config import get_settings
from app.core.logging import get_logger

from app.models.model_registry import Model, ModelStatus, ModelType
from app.services.embedding_model_config_service import EmbeddingModelConfigService
from app.services.llm_connection_resolver import RegistryLLMConnectionResolver


logger = get_logger(__name__)


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

    async def _call(self, operation: str, payload: dict[str, Any], *, models: dict[str, Any] | None = None,
                    on_progress: Callable[[dict[str, Any]], Awaitable[None]] | None = None) -> dict[str, Any]:
        settings = get_settings()
        models = models if models is not None else await self._models()
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
                data = result.json()
                if operation.startswith("documents/") and data.get("operation_id"):
                    deadline = monotonic() + settings.HIPPO_TIMEOUT_SECONDS
                    while True:
                        if on_progress:
                            await on_progress(data)
                        if data["status"] == "completed":
                            return data
                        if data["status"] == "cancelled":
                            return data
                        if data["status"] == "failed":
                            raise RuntimeError(data.get("error") or "LongMemory operation failed")
                        if monotonic() >= deadline:
                            raise TimeoutError("LongMemory operation did not finish within its time budget")
                        await asyncio.sleep(settings.HIPPO_PROGRESS_POLL_SECONDS)
                        response = await client.get(f"{settings.HIPPO_WORKER_URL.rstrip('/')}/portal/operations/{data['operation_id']}")
                        response.raise_for_status()
                        data = response.json()
                return data
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

    async def document_operation(self, *, operation_id: UUID, document_id: UUID, generation: int,
                                 action: str, document: dict[str, Any] | None = None,
                                 on_progress: Callable[[dict[str, Any]], Awaitable[None]] | None = None) -> dict[str, Any]:
        return await self._call(f"documents/{action}", {"operation_id": str(operation_id),
            "document_id": str(document_id), "generation": generation, "document": document}, on_progress=on_progress)

    async def corpus_statistics(self) -> dict[str, Any]:
        settings = get_settings()
        async with httpx.AsyncClient(timeout=3) as client:
            response = await client.get(f"{settings.HIPPO_WORKER_URL.rstrip('/')}/portal/corpus/statistics")
            response.raise_for_status()
            return response.json()

    async def document_info(self, document_id: UUID) -> dict[str, Any]:
        settings = get_settings()
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{settings.HIPPO_WORKER_URL.rstrip('/')}/portal/documents/{document_id}")
            response.raise_for_status()
            return response.json()

    async def document_triples(self, document_id: UUID, *, limit: int, offset: int) -> dict[str, Any] | None:
        settings = get_settings()
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(
                f"{settings.HIPPO_WORKER_URL.rstrip('/')}/portal/documents/{document_id}/triples",
                params={"limit": limit, "offset": offset},
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            return response.json()

    async def index_document(self, *, document_id: UUID, text: str, metadata: dict[str, Any]) -> dict[str, Any]:
        return await self.index_documents([
            {"id": str(document_id), "content": text, "metadata": metadata},
        ])

    async def index_documents(self, documents: list[dict[str, Any]]) -> dict[str, Any]:
        return await self._call("corpus/index", {"documents": documents})

    async def reindex_embeddings(self) -> dict[str, Any]:
        from app.models.rag import RAGDocument
        from app.models.rag_ingest import Source
        from app.models.memory_scope import DocumentMemoryScope, MemoryScope
        rows = (await self.session.execute(select(RAGDocument.id, MemoryScope.key, Source.meta)
            .outerjoin(DocumentMemoryScope, DocumentMemoryScope.document_id == RAGDocument.id)
            .outerjoin(MemoryScope, MemoryScope.id == DocumentMemoryScope.scope_id)
            .outerjoin(Source, Source.source_id == RAGDocument.id)
            .where(RAGDocument.status != "archived"))).all()
        assignments: dict[str, list[str]] = {}
        for document_id, key, source_meta in rows:
            document_key = str(document_id)
            memory_meta = dict((source_meta or {}).get("memory") or {})
            if memory_meta.get("scope_unassigned"):
                assignments[document_key] = []
            elif document_key not in assignments or key:
                assignments.setdefault(document_key, []).append(key or "company")
        return await self._call("corpus/reindex", {"scope_assignments": assignments})

    async def search_documents(self, query: str, *, scope_keys: list[str], limit: int = 8) -> dict[str, Any]:
        """One independent result per scope, in input order, with isolated failures."""
        keys = list(dict.fromkeys(scope_keys))
        if not keys:
            return {"backend": "hipporag", "groups": [], "group_count": 0}
        # AsyncSession cannot resolve models concurrently; resolve once before fan-out.
        def failed(scope_slug: str) -> dict[str, Any]:
            return {"scope_slug": scope_slug, "status": "failed", "success": False,
                    "hits": [], "document_count": 0, "error_code": "memory_search_failed",
                    "error": "Не удалось выполнить поиск в этом скоупе"}

        try:
            models = await self._models()
        except Exception:
            logger.exception("HippoRAG search model configuration is unavailable")
            return {"backend": "hipporag", "groups": [failed(key) for key in keys], "group_count": len(keys)}

        async def search_scope(scope_slug: str) -> dict[str, Any]:
            try:
                result = await self._call("corpus/search", {
                    "query": query, "top_k": limit, "scope_slug": scope_slug,
                }, models=models)
                return {**result, "scope_slug": scope_slug, "status": "completed", "success": True}
            except Exception:
                logger.exception("HippoRAG scope search failed scope=%s", scope_slug)
                return failed(scope_slug)

        groups = await asyncio.gather(*(search_scope(key) for key in keys))
        return {"backend": "hipporag", "groups": groups, "group_count": len(groups)}

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
