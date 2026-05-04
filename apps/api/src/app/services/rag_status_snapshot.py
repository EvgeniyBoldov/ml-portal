"""
Snapshot builders for SSE status streams.

build_collection_snapshot  — lightweight per-doc agg_status list for the collection page.
build_document_snapshot    — full StatusGraphResponse dict for the status modal.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.rag import RAGDocument
from app.models.rag_ingest import DocumentCollectionMembership

logger = get_logger(__name__)


async def build_collection_snapshot(
    session: AsyncSession,
    collection_id: UUID,
) -> List[Dict[str, Any]]:
    """Return [{document_id, agg_status, agg_details, name}] for all active docs in collection.

    RAGDocument.id == Source.source_id == DocumentCollectionMembership.source_id
    """
    stmt = (
        select(RAGDocument)
        .join(
            DocumentCollectionMembership,
            DocumentCollectionMembership.source_id == RAGDocument.id,
        )
        .where(
            DocumentCollectionMembership.collection_id == collection_id,
            RAGDocument.status != "archived",
        )
    )
    result = await session.execute(stmt)
    docs = result.scalars().all()

    items = []
    for doc in docs:
        items.append(
            {
                "document_id": str(doc.id),
                "name": doc.name or doc.filename,
                "agg_status": doc.agg_status or doc.status,
                "agg_details": {
                    k: v
                    for k, v in (doc.agg_details_json or {}).items()
                    if k in ("effective_status", "effective_reason", "policy", "counters")
                },
                "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
            }
        )
    return items


async def build_document_snapshot(
    session: AsyncSession,
    doc_id: UUID,
    repo_factory: Any,
) -> Optional[Dict[str, Any]]:
    """Return a StatusGraphResponse-compatible dict for a specific document."""
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

    try:
        status_repo = AsyncRAGStatusRepository(session)
        pipeline_nodes = await status_repo.get_pipeline_nodes(doc_id)
        embedding_nodes = await status_repo.get_embedding_nodes(doc_id)
        index_nodes = await status_repo.get_index_nodes(doc_id)

        status_manager = RAGStatusManager(session, repo_factory)
        target_models = await status_manager._get_target_models(doc_id)

        agg_status, agg_details = calculate_aggregate_status(
            doc_id=doc_id,
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
        _active = {"processing", "completed", "failed", "queued"}

        embedding_models = []
        for node in embedding_nodes:
            if node.node_key not in target_set and node.status not in _active:
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
        existing = {em.model for em in embedding_models}
        for model in target_models:
            if model not in existing:
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

        relevant_keys = {em.model for em in embedding_models}
        index_models = []
        for node in index_nodes:
            if node.node_key not in relevant_keys and node.status not in _active:
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
        existing_idx = {im.model for im in index_models}
        for em in embedding_models:
            if em.model not in existing_idx:
                index_models.append(
                    EmbeddingModel(
                        model=em.model,
                        version=em.version,
                        status="pending",
                        error=None,
                        metrics=None,
                        started_at=None,
                        finished_at=None,
                        updated_at=datetime.now(timezone.utc).isoformat(),
                    )
                )

        clean_details = {k: v for k, v in agg_details.items() if k != "pipeline"}
        ingest_policy = await status_manager.get_ingest_policy(doc_id)

        graph = StatusGraphResponse(
            doc_id=str(doc_id),
            pipeline=pipeline_stages,
            embeddings=embedding_models,
            index=index_models,
            agg_status=agg_status,
            agg_details=clean_details,
            ingest_policy=IngestPolicyResponse(
                archived=bool(ingest_policy["archived"]),
                start_allowed=bool(ingest_policy["start_allowed"]),
                start_reason=ingest_policy.get("start_reason"),
                active_stages=list(ingest_policy.get("active_stages", [])),
                retryable_stages=list(ingest_policy.get("retryable_stages", [])),
                stoppable_stages=list(ingest_policy.get("stoppable_stages", [])),
                controls=[StageControl(**c) for c in ingest_policy.get("controls", [])],
            ),
        )
        return graph.model_dump()
    except Exception as e:
        logger.error(f"Failed to build document snapshot for {doc_id}: {e}", exc_info=True)
        return None
