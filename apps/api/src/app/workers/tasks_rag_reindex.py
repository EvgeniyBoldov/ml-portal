from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, Optional

from app.celery_app import app as celery_app
from app.core.logging import get_logger
from app.services.rag_batch_reindex_orchestrator import RAGBatchReindexOrchestrator
from app.workers.session_factory import get_worker_session

logger = get_logger(__name__)


@celery_app.task(
    queue="maintenance.default",
    bind=True,
    max_retries=1,
)
def reconcile_stale_rag_reindex(
    self,
    tenant_id: Optional[str] = None,
    model_alias: Optional[str] = None,
    limit: int = 100,
) -> Dict[str, Any]:
    async def _run() -> Dict[str, Any]:
        async with get_worker_session() as session:
            orchestrator = RAGBatchReindexOrchestrator(session)
            result = await orchestrator.enqueue_stale_documents(
                tenant_id=uuid.UUID(tenant_id) if tenant_id else None,
                model_alias=model_alias,
                limit=limit,
                dry_run=False,
            )
            await session.commit()
            payload = {
                "tenant_id": tenant_id,
                "model_alias": model_alias,
                "scanned": result.scanned,
                "queued": result.queued,
                "skipped": result.skipped,
                "failed": result.failed,
                "items": result.items,
            }
            logger.info("reconcile_stale_rag_reindex_done", extra=payload)
            return payload

    return asyncio.run(_run())
