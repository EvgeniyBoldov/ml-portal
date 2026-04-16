from __future__ import annotations

import uuid
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.collection import Collection
from app.services.outbox_helper import emit_collection_vectorization_requested

logger = get_logger(__name__)


class CollectionVectorizationOrchestrator:
    """Single boundary for table-collection vectorization lifecycle."""

    def __init__(self, session: Optional[AsyncSession] = None):
        self.session = session

    @staticmethod
    def should_vectorize(collection: Collection) -> bool:
        return bool(collection.has_vector_search and collection.qdrant_collection_name)

    async def prepare_full_revectorization(self, collection: Collection) -> None:
        if not self.should_vectorize(collection):
            raise ValueError("Collection does not support vectorization")
        if self.session is None:
            raise RuntimeError("CollectionVectorizationOrchestrator requires a DB session")

        from app.services.collection_service import CollectionService

        collection_service = CollectionService(self.session)
        await collection_service._reset_table_vector_state(collection)  # noqa: SLF001
        await collection_service.sync_collection_status(collection, persist=False)
        await self.session.flush()

    async def enqueue_for_collection(
        self,
        *,
        collection: Collection,
        tenant_id: uuid.UUID,
        row_ids: Optional[Iterable[str]] = None,
        reason: str = "mutation",
        countdown: int = 3,
        emit_event: bool = True,
    ) -> Optional[str]:
        if not self.should_vectorize(collection):
            logger.debug(
                "Skipping collection vectorization enqueue for %s: vector search disabled",
                getattr(collection, "id", None),
            )
            return None

        normalized_row_ids = self._normalize_row_ids(row_ids)
        task_id = self.enqueue(
            collection_id=collection.id,
            tenant_id=tenant_id,
            row_ids=normalized_row_ids,
            countdown=countdown,
        )

        if emit_event and self.session is not None:
            await emit_collection_vectorization_requested(
                self.session,
                collection_id=collection.id,
                tenant_id=tenant_id,
                qdrant_collection_name=collection.qdrant_collection_name,
                row_ids=normalized_row_ids,
                reason=reason,
                celery_task_id=task_id,
            )

        return task_id

    @staticmethod
    def enqueue(
        *,
        collection_id: uuid.UUID | str,
        tenant_id: uuid.UUID | str,
        row_ids: Optional[Iterable[str]] = None,
        countdown: int = 3,
    ) -> str:
        from app.workers.tasks_collection_vectorize import vectorize_collection_rows

        normalized_row_ids = CollectionVectorizationOrchestrator._normalize_row_ids(row_ids)
        result = vectorize_collection_rows.apply_async(
            args=[str(collection_id), str(tenant_id), normalized_row_ids],
            countdown=countdown,
        )
        return str(result.id)

    @staticmethod
    def _normalize_row_ids(row_ids: Optional[Iterable[str]]) -> Optional[list[str]]:
        if row_ids is None:
            return None
        normalized: list[str] = []
        seen: set[str] = set()
        for row_id in row_ids:
            value = str(row_id).strip()
            if not value or value in seen:
                continue
            seen.add(value)
            normalized.append(value)
        return normalized or None

    async def reconcile_pending_collections(
        self,
        *,
        limit: int = 20,
        countdown: int = 1,
    ) -> dict:
        if self.session is None:
            raise RuntimeError("CollectionVectorizationOrchestrator requires a DB session for reconcile")

        stmt = (
            select(Collection)
            .where(
                Collection.collection_type == "table",
                Collection.is_active.is_(True),
                Collection.qdrant_collection_name.is_not(None),
                Collection.total_rows > (Collection.vectorized_rows + Collection.failed_rows),
            )
            .order_by(Collection.updated_at.asc())
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        collections = list(result.scalars().all())

        queued: list[dict[str, str]] = []
        skipped = 0
        for collection in collections:
            if not self.should_vectorize(collection):
                skipped += 1
                continue
            task_id = await self.enqueue_for_collection(
                collection=collection,
                tenant_id=collection.tenant_id,
                reason="reconcile",
                countdown=countdown,
            )
            if task_id:
                queued.append(
                    {
                        "collection_id": str(collection.id),
                        "task_id": task_id,
                    }
                )
            else:
                skipped += 1

        return {
            "queued": queued,
            "queued_count": len(queued),
            "skipped_count": skipped,
        }
