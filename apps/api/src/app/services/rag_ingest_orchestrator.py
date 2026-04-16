"""
RAGIngestOrchestrator — единственное место сборки Celery pipeline.

Отвечает за:
- Сборку chain/group для полного инжеста
- Retry отдельных стейджей
- Reindex (embed+index для новой модели)
- Резолв списка embedding-моделей
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from celery import chain, group
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.repositories.factory import AsyncRepositoryFactory
from app.schemas.common import Step
from app.services.rag_status_manager import RAGStatusManager, StageStatus
from app.workers.tasks_rag_ingest import (
    extract_document,
    normalize_document,
    chunk_document,
    embed_chunks_model,
    index_model,
)

logger = get_logger(__name__)


class RAGIngestOrchestrator:
    """Builds and dispatches Celery pipelines for RAG ingest."""

    def __init__(
        self,
        session: AsyncSession,
        repo_factory: AsyncRepositoryFactory,
        status_manager: RAGStatusManager,
    ):
        self.session = session
        self.repo_factory = repo_factory
        self.status_manager = status_manager
        self._tenant_id = str(repo_factory.tenant_id)

    # ── public API ──────────────────────────────────────

    async def start_full_pipeline(self, document_id: UUID) -> str:
        """
        Build and dispatch full ingest pipeline:
        extract → normalize → chunk → group(embed→index per model)

        Returns:
            Celery AsyncResult ID for the pipeline root task.
        """
        embedding_models = await self._resolve_embedding_models(document_id)

        await self.status_manager.start_ingest(document_id)

        pipeline = self._build_full_pipeline(document_id, embedding_models)
        result = pipeline.apply_async()

        logger.info(
            "full_pipeline_dispatched",
            extra={
                "document_id": str(document_id),
                "models": embedding_models,
                "task_id": result.id,
            },
        )
        return result.id

    async def retry_from_extract(self, document_id: UUID) -> str:
        """Retry the full pipeline starting from extract."""
        embedding_models = await self._resolve_embedding_models(document_id)

        await self.status_manager.retry_stage(document_id, "extract")

        pipeline = self._build_full_pipeline(document_id, embedding_models)
        result = pipeline.apply_async()

        logger.info(f"retry_from_extract dispatched for {document_id}, task_id={result.id}")
        return result.id

    async def retry_embed_model(self, document_id: UUID, model_alias: str, chunks_key: str) -> str:
        """Retry embed+index for a single model."""
        await self.status_manager.retry_stage(document_id, f"embed.{model_alias}")

        pipeline = self._build_embed_index_chain(document_id, model_alias, chunks_key)
        result = pipeline.apply_async()

        logger.info(f"retry_embed dispatched for {document_id}:{model_alias}, task_id={result.id}")
        return result.id

    async def reindex_with_model(self, document_id: UUID, model_alias: str, chunks_key: str) -> str:
        """
        Reindex document with a (possibly new) model.
        Initializes status nodes and dispatches embed→index.
        """
        await self.status_manager.status_repo.upsert_node(
            doc_id=document_id,
            node_type="embedding",
            node_key=model_alias,
            status=StageStatus.QUEUED.value,
        )
        await self.status_manager.status_repo.upsert_node(
            doc_id=document_id,
            node_type="index",
            node_key=model_alias,
            status=StageStatus.PENDING.value,
        )
        await self.session.flush()

        pipeline = self._build_embed_index_chain(document_id, model_alias, chunks_key)
        result = pipeline.apply_async()

        logger.info(f"reindex dispatched for {document_id}:{model_alias}, task_id={result.id}")
        return result.id

    # ── pipeline builders (pure, no side effects) ───────

    def _build_full_pipeline(self, document_id: UUID, embedding_models: List[str]) -> chain:
        """Build: extract → normalize → chunk → group(embed→index per model)."""
        doc_id = str(document_id)
        tid = self._tenant_id

        extract_sig = extract_document.s(doc_id, tid)
        normalize_sig = normalize_document.s(tid)
        chunk_sig = chunk_document.s(tid)

        embed_index_group = group(
            self._build_embed_index_sig(tid, model) for model in embedding_models
        )

        return chain(extract_sig, normalize_sig, chunk_sig, embed_index_group)

    def _build_embed_index_chain(self, document_id: UUID, model_alias: str, chunks_key: str) -> chain:
        """Build: embed → index for one model, starting from existing chunks."""
        tid = self._tenant_id
        payload = {
            "source_id": str(document_id),
            "chunks_key": chunks_key,
            "chunk_count": 0,
        }
        return chain(
            embed_chunks_model.s(payload, tid, model_alias),
            index_model.s(tid),
        )

    @staticmethod
    def _build_embed_index_sig(tenant_id: str, model_alias: str) -> chain:
        """Celery chain signature: embed → index for one model."""
        return chain(
            embed_chunks_model.s(tenant_id, model_alias),
            index_model.s(tenant_id),
        )

    # ── helpers ──────────────────────────────────────────

    async def _resolve_embedding_models(self, document_id: UUID) -> List[str]:
        """Resolve embedding models strictly from DB entities (tenant/model settings)."""
        models = await self.status_manager._get_target_models(document_id)
        if not models:
            raise ValueError(
                f"No embedding models configured for tenant {self._tenant_id}. "
                "Configure embedding models in Admin (models + defaults/tenant overrides)."
            )
        return models
