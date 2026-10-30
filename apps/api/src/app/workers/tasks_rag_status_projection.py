"""Post-commit delivery of RAG status events and collection projections."""
from __future__ import annotations

import asyncio
from uuid import UUID

from redis.asyncio import Redis
from sqlalchemy import select

from app.celery_app import app as celery_app
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.collection import Collection
from app.services.collection.status_snapshot_service import CollectionStatusSnapshotService
from app.services.rag_event_publisher import RAGEventPublisher
from app.workers.session_factory import get_worker_session

logger = get_logger(__name__)


async def _publish_events(events: list[dict]) -> None:
    settings = get_settings()
    redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        publisher = RAGEventPublisher(redis)
        for item in events:
            try:
                kind = item.get("kind")
                doc_id = UUID(item["doc_id"])
                tenant_id = UUID(item["tenant_id"])
                if kind == "initialized":
                    await publisher.publish_status_initialized(doc_id=doc_id, tenant_id=tenant_id)
                elif kind == "status_update":
                    await publisher.publish_status_update(
                        doc_id=doc_id,
                        tenant_id=tenant_id,
                        stage=item["stage"],
                        status=item["status"],
                        error=item.get("error"),
                        metrics=item.get("metrics") or {},
                    )
                elif kind == "aggregate":
                    await publisher.publish_aggregate_status(
                        doc_id=doc_id,
                        tenant_id=tenant_id,
                        agg_status=item["agg_status"],
                        agg_details=item.get("agg_details") or {},
                    )
            except Exception:
                logger.exception("Failed to publish post-commit RAG status event: %s", item.get("kind"))
    finally:
        await redis.aclose()


async def _refresh_collections(collection_ids: list[str]) -> None:
    failures: list[str] = []
    for collection_id in sorted(set(collection_ids)):
        try:
            async with get_worker_session() as session:
                collection = await session.scalar(
                    select(Collection)
                    .where(Collection.id == UUID(collection_id))
                    .with_for_update()
                    .execution_options(populate_existing=True)
                )
                if collection is None:
                    continue
                await CollectionStatusSnapshotService(session).sync_collection_status(
                    collection,
                    persist=False,
                )
                await session.commit()
        except Exception:
            logger.exception("Failed to refresh document collection status collection_id=%s", collection_id)
            failures.append(collection_id)
    if failures:
        raise RuntimeError(f"Collection status refresh failed for {len(failures)} collection(s)")


@celery_app.task(
    queue="maintenance.default",
    acks_late=True,
    reject_on_worker_lost=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def refresh_rag_status_projection(payload: dict) -> dict[str, int]:
    """Deliver committed status events and refresh affected collections."""
    async def _run() -> dict[str, int]:
        events = payload.get("events") or []
        collection_ids = payload.get("collection_ids") or []
        if events:
            await _publish_events(events)
        if collection_ids:
            await _refresh_collections(collection_ids)
        return {"events": len(events), "collections": len(collection_ids)}

    return asyncio.run(_run())


