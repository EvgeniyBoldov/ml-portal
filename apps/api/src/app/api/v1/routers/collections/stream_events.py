"""
Collection document stream read endpoints.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Optional
import uuid

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, get_current_user, get_current_user_sse, get_redis_client as redis_dependency
from app.core.logging import get_logger
from app.core.security import UserCtx
from app.core.sse import format_sse
from app.models.rag_ingest import Source
from app.repositories.factory import AsyncRepositoryFactory
from app.services.document_artifacts import get_document_artifact_key
from app.services.file_delivery_service import FileDeliveryService
from app.services.rag_event_publisher import RAGEventSubscriber

from .stream_shared import (
    _resolve_collection_and_doc,
    _resolve_document_collection,
    _document_belongs_to_collection,
)

logger = get_logger(__name__)

router = APIRouter()


@router.get("/{collection_id}/status/events")
async def stream_collection_status(
    collection_id: uuid.UUID,
    session: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(get_current_user_sse),
    redis=Depends(redis_dependency),
    document_id: Optional[str] = None,
):
    if user.role == "reader":
        raise HTTPException(status_code=403, detail="Readers do not have access to status updates")
    if not redis:
        raise HTTPException(status_code=503, detail="Redis is not available")

    await _resolve_document_collection(collection_id, session, user)
    if document_id and not await _document_belongs_to_collection(session, collection_id, uuid.UUID(document_id)):
        raise HTTPException(status_code=404, detail="Document not found in collection")

    is_admin = user.role == "admin"
    tenant_id = None if is_admin else (user.tenant_ids[0] if user.tenant_ids else None)
    cid_str = str(collection_id)
    collection_doc_cache: dict[str, bool] = {}

    async def event_generator() -> AsyncGenerator[str, None]:
        subscriber = RAGEventSubscriber(redis_client=redis, tenant_id=tenant_id, is_admin=is_admin)
        try:
            await subscriber.subscribe()
            logger.info(f"User {user.id} subscribed to collection {cid_str} status stream")
            last_heartbeat = asyncio.get_event_loop().time()
            heartbeat_interval = 30

            async for event in subscriber.listen():
                event_doc_id = event.get("document_id")
                if not event_doc_id:
                    continue
                if document_id and event_doc_id != document_id:
                    continue

                if event_doc_id not in collection_doc_cache:
                    try:
                        collection_doc_cache[event_doc_id] = await _document_belongs_to_collection(
                            session, collection_id, uuid.UUID(event_doc_id)
                        )
                    except (ValueError, TypeError):
                        collection_doc_cache[event_doc_id] = False
                if not collection_doc_cache[event_doc_id]:
                    continue

                yield format_sse(data=event, event=event.get("event_type", "status_update"))
                current_time = asyncio.get_event_loop().time()
                if current_time - last_heartbeat >= heartbeat_interval:
                    yield ": ping\n\n"
                    last_heartbeat = current_time

        except asyncio.CancelledError:
            logger.info(f"User {user.id} disconnected from collection status stream")
        except Exception as e:
            logger.error(f"Error in collection status stream: {e}")
            yield format_sse(data={"error": "Internal server error"}, event="error")
        finally:
            await subscriber.unsubscribe()

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "Access-Control-Allow-Credentials": "true",
        },
    )


@router.get("/{collection_id}/docs/{doc_id}/status-graph")
async def get_collection_doc_status_graph(
    collection_id: uuid.UUID,
    doc_id: str,
    session: AsyncSession = Depends(db_session),
    user: UserCtx = Depends(get_current_user),
):
    from app.repositories.rag_status_repo import AsyncRAGStatusRepository
    from app.services.rag_status_manager import RAGStatusManager
    from app.services.status_aggregator import calculate_aggregate_status
    from app.schemas.document_status_graph import (
        StatusGraphResponse,
        PipelineStage,
        EmbeddingModel,
        IngestPolicyResponse,
        StageControl,
    )

    collection, document, doc_uuid, repo_factory = await _resolve_collection_and_doc(
        collection_id, doc_id, session, user
    )

    try:
        status_repo = AsyncRAGStatusRepository(session)
        pipeline_nodes = await status_repo.get_pipeline_nodes(doc_uuid)
        embedding_nodes = await status_repo.get_embedding_nodes(doc_uuid)
        index_nodes = await status_repo.get_index_nodes(doc_uuid)

        status_manager = RAGStatusManager(session, repo_factory)
        target_models = await status_manager._get_target_models(doc_uuid)

        agg_status, agg_details = calculate_aggregate_status(
            doc_id=doc_uuid,
            pipeline_nodes=pipeline_nodes,
            embedding_nodes=embedding_nodes,
            target_models=target_models,
            index_nodes=index_nodes,
        )

        pipeline_stages = []
        for stage in ["upload", "extract", "normalize", "chunk", "archive"]:
            node = next((n for n in pipeline_nodes if n.node_key == stage), None)
            if node:
                pipeline_stages.append(
                    PipelineStage(
                        key=node.node_key,
                        status=node.status,
                        error=node.error_short,
                        metrics=node.metrics_json,
                        started_at=node.started_at.isoformat() if node.started_at else None,
                        finished_at=node.finished_at.isoformat() if node.finished_at else None,
                        updated_at=node.updated_at.isoformat(),
                    )
                )
            else:
                pipeline_stages.append(
                    PipelineStage(
                        key=stage,
                        status="pending",
                        error=None,
                        metrics=None,
                        started_at=None,
                        finished_at=None,
                        updated_at=datetime.now(timezone.utc).isoformat(),
                    )
                )

        target_set = set(target_models)
        _active_statuses = {"processing", "completed", "failed", "queued"}

        embedding_models = []
        for node in embedding_nodes:
            if node.node_key not in target_set and node.status not in _active_statuses:
                continue
            embedding_models.append(
                EmbeddingModel(
                    model=node.node_key,
                    version=node.model_version,
                    status=node.status,
                    error=node.error_short,
                    metrics=node.metrics_json,
                    started_at=node.started_at.isoformat() if node.started_at else None,
                    finished_at=node.finished_at.isoformat() if node.finished_at else None,
                    updated_at=node.updated_at.isoformat(),
                )
            )

        existing_models = {em.model for em in embedding_models}
        for model in target_models:
            if model not in existing_models:
                embedding_models.append(
                    EmbeddingModel(
                        model=model,
                        version=None,
                        status="pending",
                        error=None,
                        metrics=None,
                        started_at=None,
                        finished_at=None,
                        updated_at=datetime.now(timezone.utc).isoformat(),
                    )
                )

        relevant_embed_keys = {em.model for em in embedding_models}
        index_models = []
        for node in index_nodes:
            if node.node_key not in relevant_embed_keys and node.status not in _active_statuses:
                continue
            index_models.append(
                EmbeddingModel(
                    model=node.node_key,
                    version=node.model_version,
                    status=node.status,
                    error=node.error_short,
                    metrics=node.metrics_json,
                    started_at=node.started_at.isoformat() if node.started_at else None,
                    finished_at=node.finished_at.isoformat() if node.finished_at else None,
                    updated_at=node.updated_at.isoformat(),
                )
            )

        existing_index_models = {im.model for im in index_models}
        for emb_model in embedding_models:
            if emb_model.model not in existing_index_models:
                index_models.append(
                    EmbeddingModel(
                        model=emb_model.model,
                        version=emb_model.version,
                        status="pending",
                        error=None,
                        metrics=None,
                        started_at=None,
                        finished_at=None,
                        updated_at=datetime.now(timezone.utc).isoformat(),
                    )
                )

        clean_agg_details = {k: v for k, v in agg_details.items() if k != "pipeline"}
        ingest_policy = await status_manager.get_ingest_policy(doc_uuid)

        return StatusGraphResponse(
            doc_id=doc_id,
            pipeline=pipeline_stages,
            embeddings=embedding_models,
            index=index_models,
            agg_status=agg_status,
            agg_details=clean_agg_details,
            ingest_policy=IngestPolicyResponse(
                archived=bool(ingest_policy["archived"]),
                start_allowed=bool(ingest_policy["start_allowed"]),
                start_reason=ingest_policy.get("start_reason"),
                active_stages=list(ingest_policy.get("active_stages", [])),
                retryable_stages=list(ingest_policy.get("retryable_stages", [])),
                stoppable_stages=list(ingest_policy.get("stoppable_stages", [])),
                controls=[StageControl(**control) for control in ingest_policy.get("controls", [])],
            ),
        )
    except HTTPException:
        raise
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid document ID")
    except Exception as e:
        logger.error(f"Failed to get status graph: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
