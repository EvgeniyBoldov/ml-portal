from __future__ import annotations

import uuid
from typing import Any, Dict

from sqlalchemy import select

from app.celery_app import app as celery_app
from app.core.logging import get_logger
from app.models.rag_ingest import Source, DocumentCollectionMembership
from app.services.document_artifacts import normalize_document_source_meta
from app.workers.session_factory import get_worker_session

logger = get_logger(__name__)


@celery_app.task(
    queue="maintenance.default",
    bind=True,
    max_retries=1,
)
def reconcile_document_collection_memberships(self) -> Dict[str, Any]:
    """Backfill missing document_collection_memberships from legacy Source.meta bindings."""

    async def _run() -> Dict[str, Any]:
        checked = 0
        created = 0
        skipped_invalid = 0

        async with get_worker_session() as session:
            sources = (await session.execute(select(Source))).scalars().all()
            for src in sources:
                checked += 1
                meta = normalize_document_source_meta(src.meta)
                collection_id_raw = (meta.get("collection") or {}).get("id")
                if not collection_id_raw:
                    continue

                try:
                    collection_id = uuid.UUID(str(collection_id_raw))
                except (ValueError, TypeError):
                    skipped_invalid += 1
                    continue

                exists = (
                    await session.execute(
                        select(DocumentCollectionMembership.id).where(
                            DocumentCollectionMembership.source_id == src.source_id,
                            DocumentCollectionMembership.collection_id == collection_id,
                            DocumentCollectionMembership.tenant_id == src.tenant_id,
                        )
                    )
                ).scalar_one_or_none()
                if exists:
                    continue

                row_id = None
                row_id_raw = (meta.get("collection") or {}).get("row_id")
                if row_id_raw:
                    try:
                        row_id = uuid.UUID(str(row_id_raw))
                    except (ValueError, TypeError):
                        row_id = None

                session.add(
                    DocumentCollectionMembership(
                        tenant_id=src.tenant_id,
                        source_id=src.source_id,
                        collection_id=collection_id,
                        collection_row_id=row_id,
                    )
                )
                created += 1

            if created:
                await session.flush()
            await session.commit()

        logger.info(
            "reconcile_document_collection_memberships_done",
            extra={"checked": checked, "created": created, "skipped_invalid": skipped_invalid},
        )
        return {"checked": checked, "created": created, "skipped_invalid": skipped_invalid}

    import asyncio

    return asyncio.run(_run())
