"""
Status Aggregator for calculating document aggregate status
"""
from __future__ import annotations
from typing import List, Tuple, Dict, Any, Optional
from uuid import UUID
from datetime import datetime, timezone

from app.models.rag_ingest import RAGStatus


def calculate_aggregate_status(
    doc_id: UUID,
    pipeline_nodes: List[RAGStatus],
    embedding_nodes: List[RAGStatus],
    target_models: List[str],
    index_nodes: Optional[List[RAGStatus]] = None,
    *,
    archived: bool = False,
    default_model_alias: Optional[str] = None,
    tenant_secondary_model_alias: Optional[str] = None,
    model_availability: Optional[Dict[str, bool]] = None,
) -> Tuple[str, Dict[str, Any]]:
    """
    Calculate aggregate status based on pipeline and embedding nodes
    
    Args:
        doc_id: Document ID
        pipeline_nodes: List of pipeline status nodes
        embedding_nodes: List of embedding status nodes  
        target_models: List of target embedding models for tenant
        
    Returns:
        Tuple of (agg_status, agg_details_json)
        
    Logic:
        1. If pipeline has error → failed
        2. If pipeline has pending|running → processing
        3. When pipeline complete, aggregate по индексам:
           - рассматриваем только target_models
           - собираем статусы index.* (fallback к embedding.* только для деталей)
           - pending/queued/processing/missing → «ещё работает»
           - completed → готовая модель
           - failed/cancelled → модель упала

           Итоговый агрегат:
           - есть активные (pending/missing/running) → processing
           - все completed → ready
           - часть completed, часть failed/cancelled → partial
           - иначе (нет completed, всё failed/cancelled) → failed
    """
    
    # Check pipeline status first
    pipeline_statuses = {node.node_key: node.status for node in pipeline_nodes}
    
    # If any pipeline stage has failed → failed
    if any(status == 'failed' for status in pipeline_statuses.values()):
        details = {
            'pipeline': pipeline_statuses,
            'embedding': {},
            'policy': 'pipeline_error',
            'last_error': _get_last_pipeline_error(pipeline_nodes),
            'updated_at': datetime.now(timezone.utc).isoformat()
        }
        _annotate_effective_status(
            agg_details=details,
            archived=archived,
            pipeline_nodes=pipeline_nodes,
            index_nodes=index_nodes or [],
            default_model_alias=default_model_alias,
            tenant_secondary_model_alias=tenant_secondary_model_alias,
            model_availability=model_availability or {},
        )
        return 'failed', details
    
    # Special case: uploaded (upload=completed, others=pending)
    if (pipeline_statuses.get('upload') == 'completed' and 
        all(status == 'pending' for key, status in pipeline_statuses.items() if key != 'upload')):
        details = {
            'pipeline': pipeline_statuses,
            'embedding': {},
            'policy': 'uploaded',
            'updated_at': datetime.now(timezone.utc).isoformat()
        }
        _annotate_effective_status(
            agg_details=details,
            archived=archived,
            pipeline_nodes=pipeline_nodes,
            index_nodes=index_nodes or [],
            default_model_alias=default_model_alias,
            tenant_secondary_model_alias=tenant_secondary_model_alias,
            model_availability=model_availability or {},
        )
        return 'uploaded', details
    
    # If any pipeline stage is pending, queued or processing → processing
    if any(status in ['pending', 'queued', 'processing'] for status in pipeline_statuses.values()):
        agg_status = 'processing'
        agg_details = {
            'pipeline': pipeline_statuses,
            'embedding': {},
            'policy': 'pipeline_running',
            'updated_at': datetime.now(timezone.utc).isoformat(),
        }
        _annotate_effective_status(
            agg_details=agg_details,
            archived=archived,
            pipeline_nodes=pipeline_nodes,
            index_nodes=index_nodes or [],
            default_model_alias=default_model_alias,
            tenant_secondary_model_alias=tenant_secondary_model_alias,
            model_availability=model_availability or {},
        )
        return agg_status, agg_details
    
    # Pipeline is complete: анализируем индексные статусы (fallback к embedding только для деталей)
    embedding_statuses = {node.node_key: node.status for node in embedding_nodes}
    index_nodes = index_nodes or []
    index_statuses = {node.node_key: node.status for node in index_nodes}

    N = len(target_models)

    # Ранний случай: нет целевых моделей → считаем документ готовым после завершения pipeline
    if N == 0:
        agg_status = 'ready'
        policy = 'no_target_models'
        ready_models = []
        failed_models = []
        running_models = []
        missing_models = []
    else:
        ready_models: List[str] = []
        failed_models: List[str] = []
        running_models: List[str] = []
        missing_models: List[str] = []

        for model in target_models:
            status = index_statuses.get(model)
            if status is None:
                missing_models.append(model)
                continue

            if status == 'completed':
                ready_models.append(model)
            elif status in {'failed', 'cancelled'}:
                failed_models.append(model)
            elif status in {'pending', 'queued', 'processing'}:
                running_models.append(model)
            else:
                # Неожиданный статус трактуем как «ещё работает»
                running_models.append(model)

        active_models = running_models + missing_models

        if active_models:
            agg_status = 'processing'
            policy = 'index_running'
        elif len(ready_models) == N:
            agg_status = 'ready'
            policy = 'all_index_ready'
        elif ready_models and failed_models:
            agg_status = 'partial'
            policy = 'index_partial'
        elif ready_models:
            # Теоретически impossible (нет активных и failed, но есть ready < N)
            agg_status = 'partial'
            policy = 'index_partial'
        else:
            agg_status = 'failed'
            policy = 'index_all_failed'
    
    # Build details
    agg_details = {
        'pipeline': pipeline_statuses,
        'embedding': embedding_statuses,
        'index': index_statuses,
        'policy': policy,
        'counters': {
            'target_models': N,
            'ready_models': len(ready_models),
            'failed_models': len(failed_models),
            'running_models': len(running_models),
            'missing_models': len(missing_models),
        },
        'lists': {
            'ready': ready_models,
            'failed': failed_models,
            'running': running_models,
            'missing': missing_models,
        },
        'target_models': target_models,
        'updated_at': datetime.now(timezone.utc).isoformat()
    }
    
    # Add last error if any
    last_index_error = _get_last_index_error(index_nodes)
    last_embedding_error = _get_last_embedding_error(embedding_nodes)
    if last_index_error:
        agg_details['last_error'] = last_index_error
    elif last_embedding_error:
        agg_details['last_error'] = last_embedding_error
    
    _annotate_effective_status(
        agg_details=agg_details,
        archived=archived,
        pipeline_nodes=pipeline_nodes,
        index_nodes=index_nodes or [],
        default_model_alias=default_model_alias,
        tenant_secondary_model_alias=tenant_secondary_model_alias,
        model_availability=model_availability or {},
    )
    return agg_status, agg_details


def _annotate_effective_status(
    *,
    agg_details: Dict[str, Any],
    archived: bool,
    pipeline_nodes: List[RAGStatus],
    index_nodes: List[RAGStatus],
    default_model_alias: Optional[str],
    tenant_secondary_model_alias: Optional[str],
    model_availability: Dict[str, bool],
) -> None:
    """Compute user-facing availability status for document cards/search gates."""
    # Priority 1: archive short-circuit
    if archived:
        agg_details["effective_status"] = "archived"
        agg_details["effective_reason"] = "document_archived"
        return

    active_statuses = {"pending", "queued", "processing"}
    if any((n.status or "").lower() in active_statuses for n in pipeline_nodes + index_nodes):
        agg_details["effective_status"] = "processing"
        agg_details["effective_reason"] = "active_ingest_stages"
        return

    idx = {str(n.node_key): (n.status or "").lower() for n in index_nodes}
    has_any_index = any(v == "completed" for v in idx.values())

    def _is_model_available(alias: Optional[str]) -> bool:
        if not alias:
            return False
        return bool(model_availability.get(alias, False))

    def _is_index_ready(alias: Optional[str]) -> bool:
        if not alias:
            return False
        return idx.get(alias) == "completed"

    default_ok = _is_index_ready(default_model_alias) and _is_model_available(default_model_alias)
    secondary_ok = _is_index_ready(tenant_secondary_model_alias) and _is_model_available(tenant_secondary_model_alias)

    if default_ok and secondary_ok:
        agg_details["effective_status"] = "extended"
        agg_details["effective_reason"] = "default_and_secondary_available"
    elif default_ok:
        agg_details["effective_status"] = "available"
        agg_details["effective_reason"] = "default_available"
    elif secondary_ok:
        agg_details["effective_status"] = "limited"
        agg_details["effective_reason"] = "secondary_only_available"
    elif has_any_index:
        # vectors exist but all relevant models unavailable for serving
        agg_details["effective_status"] = "archived"
        agg_details["effective_reason"] = "indexes_exist_models_unavailable"
    else:
        agg_details["effective_status"] = "unavailable"
        agg_details["effective_reason"] = "no_indexes_no_active_tasks"


def _get_last_pipeline_error(pipeline_nodes: List[RAGStatus]) -> Optional[str]:
    """Get the most recent pipeline error"""
    error_nodes = [node for node in pipeline_nodes if node.status == 'failed' and node.error_short]
    if not error_nodes:
        return None
    
    # Return error from the latest updated node
    latest_error = max(error_nodes, key=lambda n: n.updated_at)
    return latest_error.error_short


def _get_last_embedding_error(embedding_nodes: List[RAGStatus]) -> Optional[str]:
    """Get the most recent embedding error"""
    error_nodes = [node for node in embedding_nodes if node.status == 'failed' and node.error_short]
    if not error_nodes:
        return None
    
    # Return error from the latest updated node
    latest_error = max(error_nodes, key=lambda n: n.updated_at)
    return latest_error.error_short


def _get_last_index_error(index_nodes: List[RAGStatus]) -> Optional[str]:
    """Get the most recent index error"""
    error_nodes = [node for node in index_nodes if node.status in {'failed', 'cancelled'} and node.error_short]
    if not error_nodes:
        return None

    latest_error = max(error_nodes, key=lambda n: n.updated_at)
    return latest_error.error_short


def is_document_stale(doc_id: UUID, embedding_nodes: List[RAGStatus], current_model_versions: Dict[str, str]) -> bool:
    """
    Check if document is stale (model versions changed)
    
    Args:
        doc_id: Document ID
        embedding_nodes: List of embedding status nodes
        current_model_versions: Current model versions from registry
        
    Returns:
        True if document needs reindexing due to model version changes
    """
    for node in embedding_nodes:
        if node.node_type == 'embedding' and node.model_version:
            current_version = current_model_versions.get(node.node_key)
            if current_version and current_version != node.model_version:
                return True
    return False
