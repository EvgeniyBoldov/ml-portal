from __future__ import annotations

import asyncio
import uuid
from typing import Any, Dict, Optional

from sqlalchemy import select

from app.celery_app import app as celery_app
from app.core.logging import get_logger
from app.models.rag import RAGDocument
from app.models.rag_ingest import RAGStatus
from app.repositories.factory import AsyncRepositoryFactory
from app.services.rag_status_manager import RAGStatusManager
from app.workers.session_factory import get_worker_session

logger = get_logger(__name__)


@celery_app.task(
    queue="maintenance.default",
    bind=True,
    max_retries=1,
)
def reconcile_rag_statuses_for_embedding_model(
    self,
    model_alias: Optional[str] = None,
    tenant_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Recompute aggregate RAG statuses after embedding-model topology/version changes.

    Filters:
    - tenant_id: recompute only documents of this tenant
    - model_alias: recompute only documents having index/embedding nodes for this alias
    If neither is provided, recompute all documents.
    """

    async def _run() -> Dict[str, Any]:
        checked = 0
        updated = 0

        async with get_worker_session() as session:
            stmt = select(RAGDocument.id, RAGDocument.tenant_id)
            if tenant_id:
                try:
                    tenant_uuid = uuid.UUID(str(tenant_id))
                    stmt = stmt.where(RAGDocument.tenant_id == tenant_uuid)
                except Exception:
                    logger.warning("invalid_tenant_id_for_reconcile", extra={"tenant_id": tenant_id})
            if model_alias:
                stmt = (
                    stmt.join(RAGStatus, RAGStatus.doc_id == RAGDocument.id)
                    .where(
                        RAGStatus.node_type.in_(["embedding", "index"]),
                        RAGStatus.node_key == str(model_alias),
                    )
                    .distinct()
                )
            rows = (await session.execute(stmt)).all()

            for doc_id, tenant_id in rows:
                checked += 1
                if not doc_id or not tenant_id:
                    continue
                try:
                    repo_factory = AsyncRepositoryFactory(session, tenant_id=tenant_id)
                    manager = RAGStatusManager(session, repo_factory)
                    await manager._update_aggregate_status(doc_id)  # noqa: SLF001
                    updated += 1
                except Exception as exc:
                    logger.warning(
                        "reconcile_rag_statuses_failed_for_document",
                        extra={
                            "doc_id": str(doc_id),
                            "tenant_id": str(tenant_id),
                            "model_alias": model_alias,
                            "error": str(exc),
                        },
                    )
            await session.commit()

        logger.info(
            "reconcile_rag_statuses_for_embedding_model_done",
            extra={"model_alias": model_alias, "tenant_id": tenant_id, "checked": checked, "updated": updated},
        )
        return {"model_alias": model_alias, "tenant_id": tenant_id, "checked": checked, "updated": updated}

    return asyncio.run(_run())
