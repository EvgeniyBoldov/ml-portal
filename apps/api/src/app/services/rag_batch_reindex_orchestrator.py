from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.model_registry import ModelRegistry
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
    - current model version exists and differs from indexed node version
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
                        "reason": "stale_model_version",
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
                await status_manager.retry_stage(uuid.UUID(doc_id), f"embed.{alias}")
                await status_manager.dispatch_stage_retry(
                    uuid.UUID(doc_id),
                    uuid.UUID(tenant),
                    f"embed.{alias}",
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
        stmt = (
            select(
                RAGStatus.doc_id,
                RAGDocument.tenant_id,
                RAGStatus.node_key,
                RAGStatus.model_version,
                ModelRegistry.model_version.label("current_model_version"),
            )
            .join(RAGDocument, RAGDocument.id == RAGStatus.doc_id)
            .join(ModelRegistry, ModelRegistry.alias == RAGStatus.node_key)
            .where(RAGStatus.node_type == "index")
            .where(RAGStatus.status == "completed")
            .where(RAGStatus.model_version.is_not(None))
            .where(ModelRegistry.model_version.is_not(None))
            .where(RAGStatus.model_version != ModelRegistry.model_version)
            .where(RAGDocument.status != "archived")
            .order_by(RAGStatus.updated_at.asc())
            .limit(max(1, min(int(limit), 500)))
        )
        if tenant_id:
            stmt = stmt.where(RAGDocument.tenant_id == tenant_id)
        if model_alias:
            stmt = stmt.where(RAGStatus.node_key == model_alias)
        result = await self.session.execute(stmt)
        return result.all()
