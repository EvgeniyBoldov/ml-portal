"""
Collection document stream read endpoints.
"""
from __future__ import annotations

import asyncio
from typing import Any, AsyncGenerator, Optional
import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, get_current_user, get_current_user_sse
from app.core.config import get_settings
from app.core.db import get_session_factory
from app.core.logging import get_logger
from app.core.security import UserCtx
from app.core.sse import format_sse
from app.repositories.factory import AsyncRepositoryFactory
from app.services.rag_event_publisher import RAGEventSubscriber
from app.services.rag_status_snapshot import build_collection_snapshot, build_document_status_graph

from .stream_shared import (
    _resolve_collection_and_doc,
    _resolve_document_collection,
)

logger = get_logger(__name__)

router = APIRouter()


_AGGREGATE_EVENT_TYPES = {
    "aggregate_update",
    "document_archived",
    "document_unarchived",
    "document_added",
    "document_deleted",
}

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _make_agg_subscriber(settings: Any, is_admin: bool, tenant_id: Optional[uuid.UUID]) -> tuple[Any, Any]:
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    subscriber = RAGEventSubscriber(redis_client=redis_client, tenant_id=tenant_id, is_admin=is_admin)
    return redis_client, subscriber


def _make_doc_subscriber(settings: Any, doc_id: uuid.UUID) -> tuple[Any, Any]:
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    subscriber = RAGEventSubscriber.for_document(redis_client=redis_client, doc_id=doc_id)
    return redis_client, subscriber


@router.get("/{collection_id}/status/events")
async def stream_collection_aggregate_status(
    collection_id: uuid.UUID,
    session: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(get_current_user_sse),
):
    """SSE stream of aggregate document status changes for a collection.

    Emits only: aggregate_update, document_archived, document_unarchived.
    Used by the collection page to refresh the document list.
    """
    if user.role == "reader":
        raise HTTPException(status_code=403, detail="Access denied")

    settings = get_settings()
    if not settings.REDIS_URL:
        raise HTTPException(status_code=503, detail="Redis is not available")

    collection = await _resolve_document_collection(collection_id, session, user)
    # DI session is only needed for the access check above.
    # Close it explicitly before handing off to the long-lived generator.
    await session.close()

    is_admin = user.role == "admin"
    tenant_id = None if is_admin else collection.tenant_id
    cid_str = str(collection_id)
    _RESYNC_INTERVAL = 60  # seconds
    _session_factory = get_session_factory()

    async def _snapshot() -> list:
        async with _session_factory() as s:
            try:
                return await build_collection_snapshot(s, collection_id)
            finally:
                await s.close()

    async def event_generator() -> AsyncGenerator[str, None]:
        redis_client, subscriber = _make_agg_subscriber(settings, is_admin, tenant_id)
        try:
            await subscriber.subscribe()
            logger.info(f"User {user.id} subscribed to collection {cid_str} aggregate stream")

            # Send initial snapshot so the client has current state immediately
            try:
                snapshot_items = await _snapshot()
                yield format_sse(
                    data={"items": snapshot_items, "collection_id": cid_str},
                    event="snapshot",
                )
            except Exception as snap_err:
                logger.warning(f"Collection snapshot failed: {snap_err}")

            last_resync = asyncio.get_event_loop().time()
            listener = subscriber.listen().__aiter__()
            while True:
                try:
                    event = await asyncio.wait_for(listener.__anext__(), timeout=15)
                except asyncio.TimeoutError:
                    # Periodic resync
                    now = asyncio.get_event_loop().time()
                    if now - last_resync >= _RESYNC_INTERVAL:
                        try:
                            snapshot_items = await _snapshot()
                            yield format_sse(
                                data={"items": snapshot_items, "collection_id": cid_str},
                                event="snapshot",
                            )
                            last_resync = now
                        except Exception as resync_err:
                            logger.warning(f"Collection resync failed: {resync_err}")
                    continue
                except StopAsyncIteration:
                    break

                event_type = event.get("event_type", "")
                if event_type not in _AGGREGATE_EVENT_TYPES:
                    continue
                if not event.get("document_id"):
                    continue

                logger.info(f"SSE collection {cid_str}: {event_type} doc={event['document_id']}")
                yield format_sse(data=event, event=event_type)

        except asyncio.CancelledError:
            logger.info(f"User {user.id} disconnected from collection {cid_str} aggregate stream")
        except Exception as e:
            logger.error(f"Collection aggregate stream error: {e}", exc_info=True)
            yield format_sse(data={"error": "Internal server error"}, event="error")
        finally:
            await subscriber.unsubscribe()
            try:
                await redis_client.aclose()
            except Exception:
                pass

    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.get("/{collection_id}/docs/{doc_id}/status/events")
async def stream_document_status(
    collection_id: uuid.UUID,
    doc_id: uuid.UUID,
    session: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(get_current_user_sse),
):
    """SSE stream of all status events for a specific document.

    Emits all event types (status_update, aggregate_update, etc.) filtered by document_id.
    Used by StatusModalNew to update the pipeline graph in real time.
    """
    if user.role == "reader":
        raise HTTPException(status_code=403, detail="Access denied")

    settings = get_settings()
    if not settings.REDIS_URL:
        raise HTTPException(status_code=503, detail="Redis is not available")

    await _resolve_collection_and_doc(collection_id, str(doc_id), session, user)
    # DI session only needed for access check — close before long-lived generator.
    await session.close()

    doc_id_str = str(doc_id)
    cid_str = str(collection_id)
    _session_factory = get_session_factory()

    async def event_generator() -> AsyncGenerator[str, None]:
        redis_client, subscriber = _make_doc_subscriber(settings, doc_id)
        try:
            await subscriber.subscribe()
            logger.info(f"User {user.id} subscribed to doc {doc_id_str} status stream")

            # Send initial snapshot with full status graph using a short-lived session
            try:
                async with _session_factory() as s:
                    try:
                        repo_factory = AsyncRepositoryFactory(s, None)
                        snapshot = await build_document_status_graph(s, doc_id, repo_factory)
                    finally:
                        await s.close()
                if snapshot:
                    yield format_sse(
                        data={"document_id": doc_id_str, "graph": snapshot},
                        event="snapshot",
                    )
            except Exception as snap_err:
                logger.warning(f"Document snapshot failed for {doc_id_str}: {snap_err}")

            listener = subscriber.listen().__aiter__()
            while True:
                try:
                    event = await asyncio.wait_for(listener.__anext__(), timeout=60)
                except asyncio.TimeoutError:
                    continue
                except StopAsyncIteration:
                    break

                event_type = event.get("event_type", "status_update")
                logger.info(f"SSE doc {doc_id_str}: {event_type}")
                yield format_sse(data=event, event=event_type)

        except asyncio.CancelledError:
            logger.info(f"User {user.id} disconnected from doc {doc_id_str} status stream")
        except Exception as e:
            logger.error(f"Document status stream error: {e}", exc_info=True)
            yield format_sse(data={"error": "Internal server error"}, event="error")
        finally:
            await subscriber.unsubscribe()
            try:
                await redis_client.aclose()
            except Exception:
                pass

    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=_SSE_HEADERS)


@router.get("/{collection_id}/docs/{doc_id}/status-graph")
async def get_collection_doc_status_graph(
    collection_id: uuid.UUID,
    doc_id: str,
    session: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(get_current_user),
):
    _collection, _document, doc_uuid, repo_factory = await _resolve_collection_and_doc(
        collection_id, doc_id, session, user
    )
    graph = await build_document_status_graph(session, doc_uuid, repo_factory)
    if graph is None:
        raise HTTPException(status_code=500, detail="Failed to build document status graph")
    return graph
