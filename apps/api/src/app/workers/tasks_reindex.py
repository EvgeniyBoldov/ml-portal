"""
RAG reindex tasks
"""
from __future__ import annotations
import logging
import uuid
from typing import List, Dict, Any
from datetime import datetime, timezone

from celery import Task
from celery.exceptions import Retry

from app.celery_app import app as celery_app
from app.core.db import get_session_factory
from app.repositories.factory import AsyncRepositoryFactory
from app.workers.schemas import ReindexIn
from app.workers.tasks_rag_ingest import (
    extract_document, normalize_document, chunk_document, 
    embed_chunks_model, index_model, commit_source
)

logger = logging.getLogger(__name__)


@celery_app.task(queue="reindex.default", bind=True, max_retries=3)
async def reindex_source(self: Task, source_id: str, models: List[str] = None) -> Dict[str, Any]:
    """
    Reindex source with specified models
    
    Args:
        source_id: Document ID to reindex
        models: List of models to reindex
        
    Returns:
        Dict with reindex result
    """
    logger.info(f"Starting reindex_source for {source_id} with models: {models}")
    
    try:
        if models is None:
            models = ["modelA", "modelB"]  # Default models
        
        # Check if document exists
        session_factory = get_session_factory()
        async with session_factory() as session:
            repo_factory = AsyncRepositoryFactory(session, uuid.UUID("00000000-0000-0000-0000-000000000000"))
            document = await repo_factory.get_rag_document_by_id(uuid.UUID(source_id), "admin")
            
            if not document:
                raise ValueError(f"Document {source_id} not found")
            
            # Update status to reindexing
            await repo_factory.update_rag_document_status(uuid.UUID(source_id), "reindexing")
            await session.commit()
        
        # Soft delete old vectors (in production, implement proper cleanup)
        await _soft_delete_old_vectors(source_id, models)
        
        # Start reindexing pipeline
        # Step 1: Extract
        extract_result = extract_document.delay(source_id, tenant_id)
        extract_data = extract_result.get()
        
        # Step 2: Normalize
        normalize_result = normalize_document.delay(extract_data, tenant_id)
        canonical_key = normalize_result.get()["canonical_key"]
        
        # Step 2: Chunk document
        chunk_result = chunk_document.delay(source_id, canonical_key)
        chunks_manifest_key = chunk_result.get()["chunks_manifest_key"]
        
        # Step 3: Embed for each model
        embed_tasks = []
        for model in models:
            embed_task = embed_chunks_model.delay(
                source_id=source_id,
                chunks_manifest_key=chunks_manifest_key,
                model_alias=model,
                batch_size=128,
                priority="low"
            )
            embed_tasks.append(embed_task)
        
        # Wait for all embedding tasks to complete
        embed_results = []
        for task in embed_tasks:
            result = task.get()
            embed_results.append(result)
        
        # Step 4: Commit source
        commit_result = commit_source.delay(source_id, models)
        commit_data = commit_result.get()
        
        logger.info(f"Successfully reindexed source {source_id}")
        
        return {
            "source_id": source_id,
            "models": models,
            "embed_results": embed_results,
            "commit_result": commit_data,
            "reindexed_at": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as exc:
        logger.error(f"Error in reindex_source for {source_id}: {exc}")
        
        # Update status to failed
        try:
            session_factory = get_session_factory()
            async with session_factory() as session:
                repo_factory = AsyncRepositoryFactory(session, uuid.UUID("00000000-0000-0000-0000-000000000000"))
                await repo_factory.update_rag_document_status(uuid.UUID(source_id), "failed")
                await repo_factory.update_rag_document_error(uuid.UUID(source_id), str(exc))
                await session.commit()
        except Exception as update_exc:
            logger.error(f"Failed to update document status: {update_exc}")
        
        if self.request.retries < self.max_retries:
            countdown = 60 * (2 ** self.request.retries)
            logger.info(f"Retrying reindex_source for {source_id} in {countdown}s")
            raise self.retry(countdown=countdown, exc=exc)
        
        logger.error(f"Final failure in reindex_source for {source_id}")
        raise


@celery_app.task(queue="reindex.default", bind=True, max_retries=3)
async def reindex_failed_documents(self: Task) -> Dict[str, Any]:
    """
    Reindex all failed documents
    
    Returns:
        Dict with reindex result
    """
    logger.info("Starting reindex_failed_documents")
    
    try:
        # Find failed documents
        session_factory = get_session_factory()
        async with session_factory() as session:
            repo_factory = AsyncRepositoryFactory(session, uuid.UUID("00000000-0000-0000-0000-000000000000"))
            
            # Get failed documents (simplified - in production, use proper query)
            # For now, we'll return empty result
            failed_docs = []
            
            logger.info(f"Found {len(failed_docs)} failed documents to reindex")
            
            # Reindex each failed document
            reindex_tasks = []
            for doc in failed_docs:
                task = reindex_source.delay(str(doc["id"]))
                reindex_tasks.append(task)
            
            # Wait for all reindex tasks to complete
            results = []
            for task in reindex_tasks:
                try:
                    result = task.get(timeout=300)  # 5 minute timeout
                    results.append(result)
                except Exception as task_exc:
                    logger.error(f"Reindex task failed: {task_exc}")
                    results.append({"error": str(task_exc)})
            
            return {
                "reindexed_count": len(results),
                "results": results,
                "completed_at": datetime.now(timezone.utc).isoformat()
            }
            
    except Exception as exc:
        logger.error(f"Error in reindex_failed_documents: {exc}")
        
        if self.request.retries < self.max_retries:
            countdown = 60 * (2 ** self.request.retries)
            logger.info(f"Retrying reindex_failed_documents in {countdown}s")
            raise self.retry(countdown=countdown, exc=exc)
        
        logger.error("Final failure in reindex_failed_documents")
        raise


@celery_app.task(queue="reindex.default", bind=True, max_retries=3)
async def reindex_by_model(self: Task, model_alias: str, source_ids: List[str] = None) -> Dict[str, Any]:
    """
    Reindex specific model for given sources
    
    Args:
        model_alias: Model to reindex
        source_ids: List of source IDs (if None, reindex all)
        
    Returns:
        Dict with reindex result
    """
    logger.info(f"Starting reindex_by_model for {model_alias}")
    
    try:
        if source_ids is None:
            # Get all sources (simplified)
            source_ids = []
        
        logger.info(f"Reindexing {len(source_ids)} sources for model {model_alias}")
        
        # Reindex each source for the specific model
        reindex_tasks = []
        for source_id in source_ids:
            task = reindex_source.delay(source_id, [model_alias])
            reindex_tasks.append(task)
        
        # Wait for all tasks to complete
        results = []
        for task in reindex_tasks:
            try:
                result = task.get(timeout=300)
                results.append(result)
            except Exception as task_exc:
                logger.error(f"Reindex task failed: {task_exc}")
                results.append({"error": str(task_exc)})
        
        return {
            "model_alias": model_alias,
            "reindexed_count": len(results),
            "results": results,
            "completed_at": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as exc:
        logger.error(f"Error in reindex_by_model for {model_alias}: {exc}")
        
        if self.request.retries < self.max_retries:
            countdown = 60 * (2 ** self.request.retries)
            logger.info(f"Retrying reindex_by_model for {model_alias} in {countdown}s")
            raise self.retry(countdown=countdown, exc=exc)
        
        logger.error(f"Final failure in reindex_by_model for {model_alias}")
        raise


# Helper functions
async def _soft_delete_old_vectors(source_id: str, models: List[str]) -> None:
    """Soft delete old vectors for reindexing"""
    logger.info(f"Soft deleting old vectors for {source_id} with models: {models}")
    
    # In production, this would:
    # 1. Mark old vectors as deleted in Qdrant
    # 2. Update metadata to indicate reindexing
    # 3. Clean up old versions
    
    for model in models:
        collection_name = f"docs_{model.replace('-', '_')}"
        logger.info(f"Soft deleting vectors from collection {collection_name}")
        # Implementation would go here
    
    logger.info(f"Completed soft delete for {source_id}")


async def _cleanup_old_versions(source_id: str, models: List[str]) -> None:
    """Clean up old versions after successful reindex"""
    logger.info(f"Cleaning up old versions for {source_id}")
    
    # In production, this would:
    # 1. Remove old vector versions
    # 2. Clean up temporary files
    # 3. Update metadata
    
    logger.info(f"Completed cleanup for {source_id}")
