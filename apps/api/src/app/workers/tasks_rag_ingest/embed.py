from __future__ import annotations
import logging
import uuid
import json
from typing import Dict, Any
from datetime import datetime, timezone

from celery import Task

from app.celery_app import app as celery_app
from app.core.config import get_settings
from app.adapters.s3_client import s3_manager
from app.adapters.embeddings import EmbeddingServiceFactory
from app.storage.paths import (
    get_embeddings_path,
    get_idempotency_key
)
from app.repositories.rag_ingest_repos import AsyncSourceRepository, AsyncChunkRepository, AsyncEmbStatusRepository
from app.repositories.factory import AsyncRepositoryFactory
from app.services.rag_status_manager import RAGStatusManager, StageStatus
from app.services.rag_event_publisher import RAGEventPublisher
from app.workers.tasks_rag_ingest.error_utils import notify_embed_error

logger = logging.getLogger(__name__)


@celery_app.task(
    queue="ingest.embed",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=5
)
def embed_chunks_model(self: Task, chunk_result: Dict[str, Any], tenant_id: str, model_alias: str = "all-MiniLM-L6-v2") -> Dict[str, Any]:
    """
    Generate embeddings for chunks using specified model

    Args:
        chunk_result: Result from chunk_document task
        tenant_id: Tenant ID
        model_alias: Model to use for embedding

    Returns:
        Dict: Embedding result
    """
    # Extract source_id from previous task result
    if isinstance(chunk_result, dict) and 'source_id' in chunk_result:
        source_id = chunk_result['source_id']
    elif isinstance(chunk_result, dict) and 'status' in chunk_result:
        # chunk_result is the dict returned from chunk_document
        # We need to get source_id from the chunk_document result structure
        source_id = chunk_result.get('source_id') or chunk_result.get('document_id')
        if not source_id:
            raise ValueError(f"Cannot extract source_id from chunk_result: {chunk_result}")
    else:
        # Fallback for direct calls - this shouldn't happen
        raise ValueError(f"Invalid chunk_result format: {chunk_result}")
    
    logger.info(f"Starting embed_chunks_model for source_id: {source_id}, model: {model_alias}")

    try:
        import asyncio

        async def _embed():
            # Use shared worker session factory
            from app.workers.session_factory import get_worker_session_factory
            from app.core.config import get_settings
            
            settings = get_settings()
            session_factory = get_worker_session_factory()
            
            # Get Redis client for distributed lock
            import redis.asyncio as redis
            redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
            
            # Distributed lock to prevent parallel execution
            lock_key = f"lock:embed:{source_id}:{model_alias}"
            
            try:
                async with redis_client.lock(lock_key, timeout=600, blocking_timeout=5):
                    async with session_factory() as session:
                        # Initialize repositories and status manager
                        repo_factory = AsyncRepositoryFactory(session, uuid.UUID(tenant_id))
                        
                        event_publisher = RAGEventPublisher(redis_client)
                        status_manager = RAGStatusManager(session, repo_factory, event_publisher)
                    
                        source_repo = AsyncSourceRepository(session, uuid.UUID(tenant_id))
                        chunk_repo = AsyncChunkRepository(session, uuid.UUID(tenant_id))
                        emb_status_repo = AsyncEmbStatusRepository(session, uuid.UUID(tenant_id))

                        # Get source and check status
                        source = await source_repo.get_by_id(uuid.UUID(source_id))
                        if not source:
                            raise ValueError(f"Source {source_id} not found")

                        if source.status != 'chunked':
                            raise ValueError(f"Source {source_id} is not chunked yet")

                        # Check idempotency
                        idem_key = get_idempotency_key(
                            uuid.UUID(tenant_id), uuid.UUID(source_id), 
                            "embed", model_alias
                        )

                        if await redis_client.exists(idem_key):
                            logger.info(f"Embedding already completed for {source_id} with {model_alias}")
                            # Ensure valid transition: QUEUED -> PROCESSING -> COMPLETED
                            await status_manager.transition_stage(
                                doc_id=uuid.UUID(source_id),
                                stage=f'embed.{model_alias}',
                                new_status=StageStatus.PROCESSING,
                                celery_task_id=self.request.id
                            )
                            await session.flush()  # Flush for SSE
                            await status_manager.transition_stage(
                                doc_id=uuid.UUID(source_id),
                                stage=f'embed.{model_alias}',
                                new_status=StageStatus.COMPLETED,
                                metrics={'status': 'already_processed', 'cached': True}
                            )
                            await session.flush()  # Flush for SSE
                            return {"status": "already_processed", "source_id": source_id}

                        # Get chunks
                        chunks = await chunk_repo.get_by_source_id(uuid.UUID(source_id))
                        if not chunks:
                            raise ValueError(f"No chunks found for source {source_id}")

                        # Mark embedding stage as processing
                        await status_manager.transition_stage(
                            doc_id=uuid.UUID(source_id),
                            stage=f'embed.{model_alias}',
                            new_status=StageStatus.PROCESSING,
                            celery_task_id=self.request.id
                        )
                        await session.flush()  # Flush for SSE
                        
                        # Get embedding service
                        embedding_service = EmbeddingServiceFactory.get_service(model_alias)
                        model_info = embedding_service.get_model_info()

                        # Create or update initial embedding status record
                        # Use create_or_update because record may already exist from chunk_document stage
                        await emb_status_repo.create_or_update(
                            source_id=uuid.UUID(source_id),
                            model_alias=model_alias,
                            total_count=len(chunks),
                            model_version=model_info.version
                        )
                        await session.flush()  # Flush for DB consistency

                        # Generate embeddings in batches
                        batch_size = 32
                        embeddings = []
                        processed_count = 0

                        for i in range(0, len(chunks), batch_size):
                            batch_chunks = chunks[i:i + batch_size]
                            batch_texts = [chunk.meta.get('text', '') if chunk.meta else '' for chunk in batch_chunks]

                            # Generate embeddings
                            batch_embeddings = await asyncio.to_thread(
                                embedding_service.embed_texts, 
                                batch_texts
                            )
                            
                            for chunk, embedding in zip(batch_chunks, batch_embeddings):
                                # Create embedding record
                                embedding_record = {
                                    "source_id": source_id,
                                    "chunk_id": chunk.chunk_id,
                                    "model_alias": model_alias,
                                    "model_version": model_info.version,
                                    "dimensions": model_info.dimensions,
                                    "vector": embedding,
                                    "created_at": datetime.now(timezone.utc).isoformat()
                                }
                                embeddings.append(embedding_record)

                            processed_count += len(batch_chunks)

                            # Update progress
                            logger.info(f"Updating done_count: processed_count={processed_count}, batch_size={len(batch_chunks)}")
                            await emb_status_repo.update_done_count(
                                uuid.UUID(source_id), 
                                model_alias, 
                                processed_count
                            )
                            
                            # Emit embed progress event via outbox
                            from app.services.outbox_helper import emit_embed_progress
                            total_chunks = len(chunks)
                            # Emit embed progress event via outbox (commit after to send events)
                            await emit_embed_progress(
                                session, repo_factory,
                                uuid.UUID(source_id),
                                model_alias,
                                done=processed_count,
                                total=total_chunks,
                                last_error=None
                            )
                            await session.flush()  # Flush to send SSE events immediately

                        # Save embeddings to S3 (optional, for debugging/maintenance)
                        if settings.SAVE_EMB_TO_S3:
                            from app.storage.paths import calculate_text_checksum
                            embeddings_content = "\n".join(json.dumps(emb, ensure_ascii=False) for emb in embeddings)
                            embeddings_checksum = calculate_text_checksum(embeddings_content)
                            
                            embeddings_key = get_embeddings_path(
                                uuid.UUID(tenant_id), uuid.UUID(source_id), model_alias, embeddings_checksum, "v1", 0
                            )
                            await s3_manager.upload_content_sync(
                                bucket=settings.S3_BUCKET_RAG,
                                key=embeddings_key,
                                content=embeddings_content.encode('utf-8'),
                                content_type="application/jsonl"
                            )

                        # NOTE: index_model запускается через Celery chain из start_ingest
                        # Не запускаем здесь, чтобы избежать дублирования
                        logger.info(f"Embeddings completed for {model_alias}, index will be triggered by chain")
                        
                        # Mark embedding stage as completed
                        await status_manager.transition_stage(
                            doc_id=uuid.UUID(source_id),
                            stage=f'embed.{model_alias}',
                            new_status=StageStatus.COMPLETED,
                            metrics={
                                'vectors': len(embeddings),
                                'processed_count': processed_count,
                                'model_version': model_info.version,
                                'dimensions': model_info.dimensions,
                            }
                        )
                        
                        # Emit final embed progress event (100% complete)
                        from app.services.outbox_helper import emit_embed_progress
                        await emit_embed_progress(
                            session, repo_factory,
                            uuid.UUID(source_id),
                            model_alias,
                            done=len(chunks),
                            total=len(chunks),
                            last_error=None
                        )
                        
                        # Flush all changes including outbox events
                        await session.flush()

                        # Store idempotency result
                        await redis_client.setex(
                            idem_key,
                            86400,
                            json.dumps({"status": "completed", "embeddings_count": len(embeddings)})
                        )
                        
                        return {
                            "source_id": source_id,
                            "model_alias": model_alias,
                            "embeddings": embeddings,
                            "embedded_count": len(embeddings),
                            "dimensions": model_info.dimensions,
                            "model_version": model_info.version,
                            "status": "completed"
                        }
            except redis.exceptions.LockError as lock_err:
                logger.warning(f"Could not acquire lock for {source_id}:{model_alias}, task may be running: {lock_err}")
                raise
            except Exception as e:
                # Handle errors within the same event loop
                logger.error(f"Error in embed task for {source_id}:{model_alias}: {e}")
                await notify_embed_error(source_id, tenant_id, model_alias, e)
                raise

        return asyncio.run(_embed())

    except Exception as e:
        # Retry will be handled by autoretry_for in task decorator
        logger.error(f"Error in embed_chunks_model for {source_id}: {e}")
        raise

