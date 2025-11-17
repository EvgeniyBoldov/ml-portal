from __future__ import annotations
import logging
import uuid
import json
from typing import List, Dict, Any
from datetime import datetime, timezone

from celery import Task

from app.celery_app import app as celery_app
from app.core.config import get_settings
from app.adapters.embeddings import EmbeddingServiceFactory
from app.storage.paths import (
    get_idempotency_key
)
from app.repositories.rag_ingest_repos import AsyncChunkRepository, AsyncEmbStatusRepository, AsyncSourceRepository
from app.repositories.factory import AsyncRepositoryFactory
from app.services.rag_status_manager import RAGStatusManager, StageStatus
from app.services.rag_event_publisher import RAGEventPublisher
from app.workers.tasks_rag_ingest.error_utils import notify_stage_error

logger = logging.getLogger(__name__)



@celery_app.task(
    queue="ingest.index",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=5
)
def index_model(self: Task, embed_result: Dict[str, Any], tenant_id: str) -> Dict[str, Any]:
    """
    Index embeddings into Qdrant vector store
    
    Args:
        embed_result: Result from embed_chunks_model task
        tenant_id: Tenant ID
    
    Returns:
        Dict: Index result
    """
    source_id = embed_result.get('source_id')
    model_alias = embed_result.get('model_alias')
    embeddings = embed_result.get('embeddings', [])
    
    logger.info(f"Starting index_model for source_id: {source_id}, model: {model_alias}")
    
    try:
        import asyncio
        
        async def _index():
            # Use shared worker session factory
            from app.workers.session_factory import get_worker_session_factory
            from app.core.config import get_settings
            
            settings = get_settings()
            session_factory = get_worker_session_factory()
            
            # Get Redis client for distributed lock
            import redis.asyncio as redis
            from redis.exceptions import LockError as RedisLockError
            redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
            
            # Distributed lock to prevent parallel execution
            lock_key = f"lock:index:{source_id}:{model_alias}"
            
            try:
                async with redis_client.lock(lock_key, timeout=600, blocking_timeout=5):
                    async with session_factory() as session:
                        repo_factory = AsyncRepositoryFactory(session, uuid.UUID(tenant_id))
                        
                        event_publisher = RAGEventPublisher(redis_client)
                        status_manager = RAGStatusManager(session, repo_factory, event_publisher)
                        
                        chunk_repo = AsyncChunkRepository(session, uuid.UUID(tenant_id))
                        
                        # Mark index stage as processing
                        await status_manager.transition_stage(
                            doc_id=uuid.UUID(source_id),
                            stage=f'index.{model_alias}',
                            new_status=StageStatus.PROCESSING,
                            celery_task_id=self.request.id
                        )
                        await session.flush()  # Trigger SSE
                        
                        # Check idempotency
                        idem_key = get_idempotency_key(
                            uuid.UUID(tenant_id), uuid.UUID(source_id),
                            "index", model_alias
                        )
                        
                        if await redis_client.exists(idem_key):
                            logger.info(f"Index already completed for {source_id} with {model_alias}")
                            await status_manager.transition_stage(
                                doc_id=uuid.UUID(source_id),
                                stage=f'index.{model_alias}',
                                new_status=StageStatus.COMPLETED,
                                metrics={'status': 'already_processed', 'cached': True}
                            )
                            await session.flush()  # Trigger SSE
                            await session.commit()  # Commit before return
                            return {"status": "already_processed", "source_id": source_id, "model_alias": model_alias}
                        
                        # If embed_result is idempotent and contains no embeddings, treat as cached no-op
                        if (embed_result.get('status') == 'already_processed' and not embed_result.get('embeddings')):
                            logger.info(f"Index no-op (cached) for {source_id} with {model_alias}")
                            await status_manager.transition_stage(
                                doc_id=uuid.UUID(source_id),
                                stage=f'index.{model_alias}',
                                new_status=StageStatus.COMPLETED,
                                metrics={'status': 'already_processed', 'cached': True, 'no_op': True}
                            )
                            await session.flush()  # Trigger SSE
                            await redis_client.setex(
                                idem_key,
                                86400,
                                json.dumps({"status": "completed", "indexed_count": 0, "cached": True})
                            )
                            await session.commit()  # Commit before return
                            return {"status": "already_processed", "source_id": source_id, "model_alias": model_alias}

                        # Get chunks for metadata
                        chunks = await chunk_repo.get_by_source_id(uuid.UUID(source_id))
                        chunk_map = {c.chunk_id: c for c in chunks}
                        
                        # Initialize Qdrant
                        from app.adapters.impl.qdrant import QdrantVectorStore
                        vector_store = QdrantVectorStore()
                        embedding_service = EmbeddingServiceFactory.get_service(model_alias)
                        model_info = embedding_service.get_model_info()
                        
                        collection_name = f"{tenant_id}__{model_alias}"
                        await vector_store.ensure_collection(collection_name, model_info.dimensions)
                        
                        # Prepare vectors for Qdrant
                        vectors = []
                        payloads = []
                        ids = []
                        
                        for emb_record in embeddings:
                            chunk_id = emb_record['chunk_id']
                            chunk = chunk_map.get(chunk_id)
                            
                            if not chunk:
                                logger.warning(f"Chunk {chunk_id} not found, skipping")
                                continue
                            
                            vectors.append(emb_record['vector'])
                            ids.append(str(uuid.uuid4()))
                            
                            payload = {
                                "tenant_id": tenant_id,
                                "source_id": source_id,
                                "chunk_id": chunk_id,
                                "page": chunk.page or 0,
                                "lang": chunk.lang or "en",
                                "mime": "text/plain",
                                "embed_model_alias": model_alias,
                                "version": model_info.version,
                                "updated_at": datetime.now(timezone.utc).isoformat(),
                                "tags": [],
                                "text": chunk.meta.get('text', '') if chunk.meta else ''
                            }
                            payloads.append(payload)
                        
                        # Upsert to Qdrant in batches
                        batch_size = 100
                        indexed_count = 0
                        
                        for i in range(0, len(vectors), batch_size):
                            batch_vectors = vectors[i:i + batch_size]
                            batch_payloads = payloads[i:i + batch_size]
                            batch_ids = ids[i:i + batch_size]
                            
                            await vector_store.upsert(collection_name, batch_vectors, batch_payloads, batch_ids)
                            indexed_count += len(batch_vectors)
                            
                            logger.info(f"Indexed {indexed_count}/{len(vectors)} vectors for {model_alias}")
                        
                        # Mark index stage as completed
                        await status_manager.transition_stage(
                            doc_id=uuid.UUID(source_id),
                            stage=f'index.{model_alias}',
                            new_status=StageStatus.COMPLETED,
                            metrics={
                                'indexed_count': indexed_count,
                                'collection': collection_name,
                                'model_version': model_info.version,
                                'dimensions': model_info.dimensions
                            }
                        )
                        
                        await session.flush()  # Trigger SSE
                        
                        # Store idempotency
                        await redis_client.setex(
                            idem_key,
                            86400,
                            json.dumps({"status": "completed", "indexed_count": indexed_count})
                        )
                        
                        await session.commit()  # Final commit
                        
                        return {
                            "source_id": source_id,
                            "model_alias": model_alias,
                            "indexed_count": indexed_count,
                            "status": "completed"
                        }
            except RedisLockError as lock_err:
                logger.warning(f"Could not acquire lock for {source_id}:{model_alias}, task may be running: {lock_err}")
                raise
            except Exception as e:
                # Handle errors within the same event loop
                logger.error(f"Error in index task for {source_id}:{model_alias}: {e}")
                await notify_stage_error(source_id, tenant_id, f'index.{model_alias}', e)
                raise
        
        return asyncio.run(_index())
    
    except Exception as e:
        # Retry will be handled by autoretry_for in task decorator
        logger.error(f"Error in index_model for {source_id}: {e}")
        raise


@celery_app.task(
    queue="ingest.commit",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=5
)
def commit_source(self: Task, embed_result: Dict[str, Any], tenant_id: str, models: List[str] = None) -> Dict[str, Any]:
    """
    Commit source processing - mark as completed

    Args:
        embed_result: Result from embed_chunks_model task
        tenant_id: Tenant ID
        models: List of models that should be processed

    Returns:
        Dict: Commit result
    """
    # Extract source_id from previous task result
    if isinstance(embed_result, dict) and 'source_id' in embed_result:
        source_id = embed_result['source_id']
    else:
        # Fallback for direct calls
        source_id = str(embed_result)
    
    logger.info(f"Starting commit_source for source_id: {source_id}")

    try:
        import asyncio

        async def _commit():
            # Use shared worker session factory (one engine per process)
            from app.workers.session_factory import get_worker_session_factory
            
            session_factory = get_worker_session_factory()
            
            async with session_factory() as session:
                # Initialize repositories
                repo_factory = AsyncRepositoryFactory(session, uuid.UUID(tenant_id))
                
                source_repo = AsyncSourceRepository(session, uuid.UUID(tenant_id))
                emb_status_repo = AsyncEmbStatusRepository(session, uuid.UUID(tenant_id))

                # Check if all embeddings are completed
                emb_statuses = await emb_status_repo.get_by_source_id(uuid.UUID(source_id))
                completed_models = []
                
                for emb_status in emb_statuses:
                    if emb_status.done_count == emb_status.total_count:
                        completed_models.append(emb_status.model_alias)
                
                # Update aggregate status via status manager if embeddings complete
                if completed_models:
                    logger.info(f"Archive complete for {source_id}, models: {completed_models}")
                    logger.info(f"Source {source_id} marked as ready with completed models: {completed_models}")
                else:
                    logger.warning(f"Source {source_id} embeddings not completed yet")

                return {
                    "source_id": source_id,
                    "status": "completed",
                    "completed_models": completed_models,
                    "committed_at": datetime.now(timezone.utc).isoformat()
                }

        return asyncio.run(_commit())

    except Exception as e:
        # Retry will be handled by autoretry_for in task decorator
        logger.error(f"Error in commit_source for {source_id}: {e}")
        raise