from __future__ import annotations

import asyncio
from typing import Any, Dict

from sqlalchemy import func, select

from app.adapters.impl.qdrant import QdrantVectorStore
from app.celery_app import app as celery_app
from app.core.logging import get_logger
from app.models.collection import Collection
from app.models.rag_ingest import DocumentCollectionMembership
from app.workers.session_factory import get_worker_session

logger = get_logger(__name__)


def _extract_points_count(info: Any) -> int | None:
    if info is None:
        return None
    direct = getattr(info, "points_count", None)
    if direct is not None:
        try:
            return int(direct)
        except Exception:
            return None

    payload = getattr(info, "model_dump", None)
    if callable(payload):
        raw = payload(exclude_none=True)
        value = raw.get("points_count")
        if value is None:
            value = (raw.get("result") or {}).get("points_count")
        if value is not None:
            try:
                return int(value)
            except Exception:
                return None
    return None


@celery_app.task(
    queue="maintenance.default",
    bind=True,
    max_retries=1,
)
def audit_collection_vector_indexes(self) -> Dict[str, Any]:
    async def _run() -> Dict[str, Any]:
        async with get_worker_session() as session:
            rows = (
                await session.execute(
                    select(Collection).where(
                        Collection.collection_type == "document",
                        Collection.is_active.is_(True),
                        Collection.has_vector_search.is_(True),
                        Collection.qdrant_collection_name.is_not(None),
                    )
                )
            ).scalars().all()

            vector_store = QdrantVectorStore()
            scanned = 0
            mismatched = 0
            missing = 0
            healthy = 0
            details: list[dict[str, Any]] = []

            for collection in rows:
                scanned += 1
                qdrant_name = str(collection.qdrant_collection_name or "")
                exists = await vector_store.collection_exists(qdrant_name)
                doc_count = int(
                    (
                        await session.execute(
                            select(func.count(DocumentCollectionMembership.source_id)).where(
                                DocumentCollectionMembership.collection_id == collection.id,
                                DocumentCollectionMembership.tenant_id == collection.tenant_id,
                            )
                        )
                    ).scalar()
                    or 0
                )

                if not exists:
                    missing += 1
                    mismatched += 1
                    details.append(
                        {
                            "collection_id": str(collection.id),
                            "slug": collection.slug,
                            "reason": "missing_qdrant_collection",
                            "qdrant_collection_name": qdrant_name,
                            "documents": doc_count,
                        }
                    )
                    logger.warning(
                        "collection_vector_index_missing",
                        extra={
                            "collection_id": str(collection.id),
                            "slug": collection.slug,
                            "tenant_id": str(collection.tenant_id),
                            "qdrant_collection_name": qdrant_name,
                            "documents": doc_count,
                        },
                    )
                    continue

                points_count = None
                try:
                    info = await vector_store._client.get_collection(collection_name=qdrant_name)
                    points_count = _extract_points_count(info)
                except Exception as exc:
                    mismatched += 1
                    details.append(
                        {
                            "collection_id": str(collection.id),
                            "slug": collection.slug,
                            "reason": "qdrant_get_collection_failed",
                            "error": str(exc),
                        }
                    )
                    logger.warning(
                        "collection_vector_index_info_failed",
                        extra={
                            "collection_id": str(collection.id),
                            "slug": collection.slug,
                            "qdrant_collection_name": qdrant_name,
                            "error": str(exc),
                        },
                    )
                    continue

                total_chunks = int(collection.total_chunks or 0)
                if doc_count > 0 and (points_count is None or points_count <= 0):
                    mismatched += 1
                    details.append(
                        {
                            "collection_id": str(collection.id),
                            "slug": collection.slug,
                            "reason": "documents_present_but_no_vectors",
                            "documents": doc_count,
                            "points_count": points_count,
                            "total_chunks": total_chunks,
                        }
                    )
                    logger.warning(
                        "collection_vector_index_empty",
                        extra={
                            "collection_id": str(collection.id),
                            "slug": collection.slug,
                            "qdrant_collection_name": qdrant_name,
                            "documents": doc_count,
                            "points_count": points_count,
                            "total_chunks": total_chunks,
                        },
                    )
                    continue

                if points_count is not None and total_chunks > 0 and points_count != total_chunks:
                    mismatched += 1
                    details.append(
                        {
                            "collection_id": str(collection.id),
                            "slug": collection.slug,
                            "reason": "chunks_points_mismatch",
                            "points_count": points_count,
                            "total_chunks": total_chunks,
                        }
                    )
                    logger.warning(
                        "collection_vector_index_stats_mismatch",
                        extra={
                            "collection_id": str(collection.id),
                            "slug": collection.slug,
                            "qdrant_collection_name": qdrant_name,
                            "points_count": points_count,
                            "total_chunks": total_chunks,
                        },
                    )
                    continue

                healthy += 1

            payload = {
                "scanned": scanned,
                "healthy": healthy,
                "mismatched": mismatched,
                "missing_qdrant": missing,
                "details": details,
            }
            logger.info("collection_vector_index_audit_done", extra=payload)
            return payload

    return asyncio.run(_run())

