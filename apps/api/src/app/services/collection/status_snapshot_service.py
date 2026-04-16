from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection, CollectionStatus, CollectionType


class CollectionStatusSnapshotService:
    """Computes and persists effective collection readiness snapshots."""

    _TABLE_LIFECYCLE_STAGES = (
        CollectionStatus.CREATED.value,
        CollectionStatus.INGESTING.value,
        CollectionStatus.READY.value,
        CollectionStatus.DEGRADED.value,
        CollectionStatus.ERROR.value,
    )
    _DOCUMENT_LIFECYCLE_STAGES = (
        CollectionStatus.CREATED.value,
        CollectionStatus.INGESTING.value,
        CollectionStatus.READY.value,
        CollectionStatus.DEGRADED.value,
        CollectionStatus.ERROR.value,
    )

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_status_snapshot(self, collection: Collection) -> dict[str, Any]:
        if collection.is_remote:
            return self.get_remote_status_snapshot(collection)
        if collection.collection_type == CollectionType.DOCUMENT.value:
            return await self.get_document_status_snapshot(collection)
        return await self.get_table_status_snapshot(collection)

    async def sync_collection_status(
        self,
        collection: Collection,
        *,
        persist: bool = True,
    ) -> dict[str, Any]:
        snapshot = await self.get_status_snapshot(collection)
        collection.status = snapshot["status"]
        if persist:
            self.session.add(collection)
            await self.session.flush()
        return snapshot

    def get_remote_status_snapshot(self, collection: Collection) -> dict[str, Any]:
        has_instance = collection.data_instance_id is not None
        has_schema = bool(collection.table_schema)

        if not has_instance:
            status = CollectionStatus.CREATED.value
            reason = "no_data_instance_linked"
        elif not has_schema and not collection.fields:
            status = CollectionStatus.CREATED.value
            reason = "no_schema_discovered"
        elif has_schema or collection.fields:
            status = CollectionStatus.READY.value
            reason = "schema_available"
        else:
            status = collection.status
            reason = "unknown"

        return {
            "status": status,
            "details": {
                "reason": reason,
                "has_data_instance": has_instance,
                "has_table_schema": has_schema,
                "has_fields": bool(collection.fields),
            },
        }

    async def get_table_status_snapshot(self, collection: Collection) -> dict[str, Any]:
        total_rows = int(collection.total_rows or 0)
        vectorized_rows = int(collection.vectorized_rows or 0)
        failed_rows = int(collection.failed_rows or 0)
        pending_rows = max(total_rows - vectorized_rows - failed_rows, 0)
        has_vector = bool(collection.has_vector_search and collection.qdrant_collection_name)

        if total_rows == 0:
            status = CollectionStatus.CREATED.value
            reason = "no_rows"
        elif not has_vector:
            status = CollectionStatus.READY.value
            reason = "rows_available_no_vector_required"
        elif pending_rows > 0:
            status = CollectionStatus.INGESTING.value
            reason = "vectorization_in_progress"
        elif failed_rows == 0 and vectorized_rows == total_rows:
            status = CollectionStatus.READY.value
            reason = "all_rows_vectorized"
        elif failed_rows == total_rows and vectorized_rows == 0:
            status = CollectionStatus.ERROR.value
            reason = "all_rows_vectorization_failed"
        else:
            status = CollectionStatus.DEGRADED.value
            reason = "partial_vectorization_failures"

        return {
            "status": status,
            "details": {
                "kind": CollectionType.TABLE.value,
                "lifecycle_stages": list(self._TABLE_LIFECYCLE_STAGES),
                "status_reason": reason,
                "total_rows": total_rows,
                "vectorized_rows": vectorized_rows,
                "failed_rows": failed_rows,
                "pending_rows": pending_rows,
                "has_vector_search": bool(collection.has_vector_search),
                "is_fully_vectorized": bool(collection.is_fully_vectorized),
            },
        }

    async def get_document_status_snapshot(self, collection: Collection) -> dict[str, Any]:
        result = await self.session.execute(
            text(
                "SELECT rd.agg_status, rd.status "
                "FROM ragdocuments rd "
                "JOIN sources src ON src.source_id = rd.id "
                "WHERE "
                "((src.meta #>> '{collection,id}') = :collection_id OR (src.meta ->> 'collection_id') = :collection_id)"
            ),
            {"collection_id": str(collection.id)},
        )
        statuses = [
            str(row.agg_status or row.status or "").lower()
            for row in result.all()
        ]

        total_docs = len(statuses)
        ready_docs = sum(status == "ready" for status in statuses)
        active_docs = sum(status in {"uploaded", "processing", "queued"} or not status for status in statuses)
        failed_docs = sum(status == "failed" for status in statuses)
        degraded_docs = sum(status == "partial" for status in statuses)
        archived_docs = sum(status == "archived" for status in statuses)

        if total_docs == 0:
            status = CollectionStatus.CREATED.value
            reason = "no_documents"
        elif active_docs > 0:
            status = CollectionStatus.INGESTING.value
            reason = "pipeline_in_progress"
        elif ready_docs == total_docs:
            status = CollectionStatus.READY.value
            reason = "all_documents_ready"
        elif failed_docs == total_docs:
            status = CollectionStatus.ERROR.value
            reason = "all_documents_failed"
        else:
            status = CollectionStatus.DEGRADED.value
            reason = "partial_document_failures"

        return {
            "status": status,
            "details": {
                "kind": CollectionType.DOCUMENT.value,
                "lifecycle_stages": list(self._DOCUMENT_LIFECYCLE_STAGES),
                "status_reason": reason,
                "total_documents": total_docs,
                "ready_documents": ready_docs,
                "active_documents": active_docs,
                "failed_documents": failed_docs,
                "degraded_documents": degraded_docs,
                "archived_documents": archived_docs,
            },
        }
