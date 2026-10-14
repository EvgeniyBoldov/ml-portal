from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select, and_, or_, exists
from sqlalchemy.orm import aliased
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.model_registry import ModelRegistry, ModelType, ModelStatus
from app.models.tenant import Tenants
from app.services.model_capabilities import embedding_fingerprint
from app.models.rag import RAGDocument
from app.models.rag_ingest import RAGStatus
from app.repositories.factory import AsyncRepositoryFactory
from app.services.rag_status_manager import RAGStatusManager

logger = get_logger(__name__)


@dataclass
class BatchReindexResult:
    scanned: int
    queued: int
    skipped: int
    failed: int
    items: list[dict[str, str]]


class RAGBatchReindexOrchestrator:
    """
    Batch orchestration for stale document reindex.

    Stale criteria:
    - has completed `index` node for model alias
    - vector-space fingerprint differs or is absent (legacy indexes)
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def enqueue_stale_documents(
        self,
        *,
        tenant_id: Optional[uuid.UUID] = None,
        model_alias: Optional[str] = None,
        limit: int = 100,
        dry_run: bool = False,
    ) -> BatchReindexResult:
        stale_rows = await self._load_stale_rows(
            tenant_id=tenant_id,
            model_alias=model_alias,
            limit=limit,
        )

        scanned = len(stale_rows)
        if dry_run:
            return BatchReindexResult(
                scanned=scanned,
                queued=0,
                skipped=0,
                failed=0,
                items=[
                    {
                        "doc_id": str(row.doc_id),
                        "tenant_id": str(row.tenant_id),
                        "model_alias": str(row.node_key),
                        "reason": "stale_embedding_configuration",
                    }
                    for row in stale_rows
                ],
            )

        queued = 0
        skipped = 0
        failed = 0
        items: list[dict[str, str]] = []
        seen: set[tuple[str, str]] = set()

        for row in stale_rows:
            doc_id = str(row.doc_id)
            tenant = str(row.tenant_id)
            alias = str(row.node_key)
            key = (doc_id, alias)
            if key in seen:
                skipped += 1
                continue
            seen.add(key)
            try:
                repo_factory = AsyncRepositoryFactory(self.session, tenant_id=uuid.UUID(tenant))
                status_manager = RAGStatusManager(self.session, repo_factory)
                from app.services.rag_ingest_service import RAGIngestService
                await RAGIngestService(self.session, repo_factory, status_manager).reindex_document(
                    uuid.UUID(doc_id), alias
                )
                queued += 1
                items.append(
                    {
                        "doc_id": doc_id,
                        "tenant_id": tenant,
                        "model_alias": alias,
                        "status": "queued",
                    }
                )
            except Exception as exc:
                failed += 1
                items.append(
                    {
                        "doc_id": doc_id,
                        "tenant_id": tenant,
                        "model_alias": alias,
                        "status": "failed",
                        "error": str(exc),
                    }
                )
                logger.warning(
                    "batch_reindex_enqueue_failed",
                    extra={
                        "doc_id": doc_id,
                        "tenant_id": tenant,
                        "model_alias": alias,
                        "error": str(exc),
                    },
                )

        return BatchReindexResult(
            scanned=scanned,
            queued=queued,
            skipped=skipped,
            failed=failed,
            items=items,
        )

    async def _load_stale_rows(
        self,
        *,
        tenant_id: Optional[uuid.UUID],
        model_alias: Optional[str],
        limit: int,
    ):
        models_stmt = select(ModelRegistry).where(
            ModelRegistry.type == ModelType.EMBEDDING,
            ModelRegistry.enabled.is_(True), ModelRegistry.deleted_at.is_(None),
            ModelRegistry.status == ModelStatus.AVAILABLE,
        ).order_by(ModelRegistry.created_at.asc())
        models = list((await self.session.execute(models_stmt)).scalars().all())
        default = next((model.alias for model in models if model.default_for_type),
                       models[0].alias if models else None)
        stale_conditions = []
        selected_conditions = []
        for model in models:
            if model_alias and model.alias != model_alias:
                continue
            try:
                fingerprint = embedding_fingerprint(model)
            except ValueError:
                logger.warning("Model %s needs capability verification before reindex", model.alias)
                continue
            selected = True if model_alias or model.alias == default else Tenants.embedding_model_alias == model.alias
            selected_conditions.append(and_(ModelRegistry.alias == model.alias, selected))
            stale_conditions.append(and_(ModelRegistry.alias == model.alias,
                RAGStatus.metrics_json["embedding_fingerprint"].astext.is_distinct_from(fingerprint)))
        if not stale_conditions:
            return []
        chunk_stage = aliased(RAGStatus)
        embedding_stage = aliased(RAGStatus)
        chunks_ready = exists(select(chunk_stage.id).where(
            chunk_stage.doc_id == RAGDocument.id, chunk_stage.node_type == "pipeline",
            chunk_stage.node_key == "chunk", chunk_stage.status == "completed"))
        embedding_active = exists(select(embedding_stage.id).where(
            embedding_stage.doc_id == RAGDocument.id, embedding_stage.node_type == "embedding",
            embedding_stage.node_key == ModelRegistry.alias,
            embedding_stage.status.in_(["processing", "queued"])))
        stmt = (
            select(RAGDocument.id.label("doc_id"), RAGDocument.tenant_id, ModelRegistry.alias.label("node_key"))
            .join(Tenants, Tenants.id == RAGDocument.tenant_id)
            .join(ModelRegistry, or_(*selected_conditions))
            .outerjoin(RAGStatus, and_(RAGStatus.doc_id == RAGDocument.id,
                       RAGStatus.node_key == ModelRegistry.alias, RAGStatus.node_type == "index"))
            .where(or_(
                and_(RAGStatus.status.in_(["completed", "failed"]), or_(*stale_conditions)),
                and_(or_(RAGStatus.id.is_(None), RAGStatus.status == "pending"), chunks_ready)))
            .where(~embedding_active)
            .where(RAGDocument.status != "archived")
            .order_by(RAGDocument.created_at.asc(), ModelRegistry.alias)
            .limit(max(1, min(int(limit), 500)))
        )
        if tenant_id:
            stmt = stmt.where(RAGDocument.tenant_id == tenant_id)
        result = await self.session.execute(stmt)
        return result.all()
