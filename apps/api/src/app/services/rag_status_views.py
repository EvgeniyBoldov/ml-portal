"""
Presentation / policy helpers for RAG status manager.
"""
from __future__ import annotations

from typing import Any, Dict, List
from uuid import UUID

from app.models.rag import RAGDocument
from app.services.rag_status_policy import (
    StageStatus,
    STOPPABLE_STAGE_STATUSES,
    build_stage_control,
)


async def build_ingest_policy(status_repo, target_models_service, doc_id: UUID) -> Dict[str, Any]:
    pipeline_nodes = await status_repo.get_pipeline_nodes(doc_id)
    embedding_nodes = await status_repo.get_embedding_nodes(doc_id)
    index_nodes = await status_repo.get_index_nodes(doc_id)
    target_models = await target_models_service.get_target_models(doc_id)
    effective_models = sorted(
        set(target_models)
        | {node.node_key for node in embedding_nodes}
        | {node.node_key for node in index_nodes}
    )

    archive_node = await status_repo.get_node(doc_id, "archive", "archive")
    archived = archive_node is not None

    controls: list[dict[str, Any]] = []
    node_map: dict[tuple[str, str], Any] = {}
    for node in pipeline_nodes + embedding_nodes + index_nodes:
        node_map[(node.node_type, node.node_key)] = node

    stage_order = ["upload", "extract", "normalize", "chunk"]
    for stage_name in stage_order:
        node = node_map.get(("pipeline", stage_name))
        status = node.status if node else StageStatus.PENDING.value
        controls.append(
            build_stage_control(
                stage=stage_name,
                node_type="pipeline",
                status=status,
                archived=archived,
            )
        )

    for model_alias in effective_models:
        embed_node = node_map.get(("embedding", model_alias))
        embed_status = embed_node.status if embed_node else StageStatus.PENDING.value
        controls.append(
            build_stage_control(
                stage=f"embed.{model_alias}",
                node_type="embedding",
                status=embed_status,
                archived=archived,
            )
        )

        index_node = node_map.get(("index", model_alias))
        index_status = index_node.status if index_node else StageStatus.PENDING.value
        controls.append(
            build_stage_control(
                stage=f"index.{model_alias}",
                node_type="index",
                status=index_status,
                archived=archived,
            )
        )

    active_stages = [item["stage"] for item in controls if item["status"] in STOPPABLE_STAGE_STATUSES]
    retryable_stages = [item["stage"] for item in controls if item["can_retry"]]
    stoppable_stages = [item["stage"] for item in controls if item["can_stop"]]

    start_reason = None
    if archived:
        start_allowed = False
        start_reason = "document_archived"
    elif active_stages:
        start_allowed = False
        start_reason = "ingest_already_running"
    else:
        start_allowed = True

    return {
        "archived": archived,
        "start_allowed": start_allowed,
        "start_reason": start_reason,
        "active_stages": active_stages,
        "retryable_stages": retryable_stages,
        "stoppable_stages": stoppable_stages,
        "controls": controls,
    }


async def build_document_status(status_repo, doc_id: UUID) -> Dict[str, Any]:
    pipeline_nodes = await status_repo.get_pipeline_nodes(doc_id)
    embedding_nodes = await status_repo.get_embedding_nodes(doc_id)
    index_nodes = await status_repo.get_index_nodes(doc_id)

    result = {
        "document_id": str(doc_id),
        "pipeline": {},
        "embeddings": {},
        "index": {},
        "archived": False,
    }

    for node in pipeline_nodes:
        result["pipeline"][node.node_key] = {
            "status": node.status,
            "error": node.error_short,
            "metrics": node.metrics_json,
            "started_at": node.started_at.isoformat() if node.started_at else None,
            "finished_at": node.finished_at.isoformat() if node.finished_at else None,
            "updated_at": node.updated_at.isoformat(),
        }

    for node in embedding_nodes:
        result["embeddings"][node.node_key] = {
            "status": node.status,
            "model_version": node.model_version,
            "error": node.error_short,
            "metrics": node.metrics_json,
            "started_at": node.started_at.isoformat() if node.started_at else None,
            "finished_at": node.finished_at.isoformat() if node.finished_at else None,
            "updated_at": node.updated_at.isoformat(),
        }

    for node in index_nodes:
        result["index"][node.node_key] = {
            "status": node.status,
            "model_version": node.model_version,
            "error": node.error_short,
            "metrics": node.metrics_json,
            "started_at": node.started_at.isoformat() if node.started_at else None,
            "finished_at": node.finished_at.isoformat() if node.finished_at else None,
            "updated_at": node.updated_at.isoformat(),
        }

    archive_node = await status_repo.get_node(doc_id, "archive", "archive")
    if archive_node:
        result["archived"] = True

    return result
