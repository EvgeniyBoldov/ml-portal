from __future__ import annotations
from app.core.logging import get_logger
import uuid
import json
import time
from typing import Dict, Any
from datetime import datetime, timezone

from celery import Task

from app.celery_app import app as celery_app
from app.core.config import get_settings
from app.adapters.s3_client import s3_manager
from app.adapters.embeddings import EmbeddingServiceFactory
from app.storage.paths import (
    get_embeddings_path,
    get_idempotency_key,
    calculate_text_checksum
)
from app.repositories.rag_ingest_repos import AsyncSourceRepository, AsyncEmbStatusRepository
from app.repositories.factory import AsyncRepositoryFactory
from app.services.rag_status_manager import RAGStatusManager, StageStatus
from app.services.rag_event_publisher import RAGEventPublisher
from app.workers.tasks_rag_ingest.error_utils import notify_embed_error
from app.workers.session_factory import get_worker_session

logger = get_logger(__name__)


@celery_app.task(
    queue="ingest.embed",
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
)
def embed_chunks_model(self: Task, chunk_result: Dict[str, Any], tenant_id: str, model_alias: str = "all-MiniLM-L6-v2") -> Dict[str, Any]:
    """
    Generate embeddings for chunks using specified model.
    
    Flow:
    1. Read chunks from S3 (chunks.jsonl)
    2. Generate embeddings in batches
    3. Write embeddings to S3 (embeddings.jsonl)
    4. Return path to embeddings dump
    
    Args:
        chunk_result: Result from chunk_document task
        tenant_id: Tenant ID
        model_alias: Model to use for embedding
    
    Returns:
        Dict: Embedding result with embeddings_key (s3 path)
    """
    if isinstance(chunk_result, dict) and 'source_id' in chunk_result:
        source_id = chunk_result['source_id']
        chunks_key = chunk_result.get('chunks_key')
    else:
        # Fallback (should not happen)
        source_id = str(chunk_result)
        chunks_key = None
    
    logger.info(f"Starting embed_chunks_model for source_id: {source_id}, model: {model_alias}")

    try:
        import asyncio

        async def _embed():
            start_time = time.monotonic()
            settings = get_settings()
            
            import redis.asyncio as redis
            redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
            
            # Lock is good to prevent duplicate embedding of the same model/doc
            lock_key = f"lock:embed:{source_id}:{model_alias}"
            
            try:
                # Use lock with timeout
                async with redis_client.lock(lock_key, timeout=600, blocking_timeout=5):
                    async with get_worker_session() as session:
                        repo_factory = AsyncRepositoryFactory(session, uuid.UUID(tenant_id))
                        event_publisher = RAGEventPublisher(redis_client)
                        status_manager = RAGStatusManager(session, repo_factory, event_publisher)
                        
                        source_repo = AsyncSourceRepository(session, uuid.UUID(tenant_id))
                        emb_status_repo = AsyncEmbStatusRepository(session, uuid.UUID(tenant_id))

                        # 1. Update status
                        await status_manager.transition_stage(
                            doc_id=uuid.UUID(source_id),
                            stage=f'embed.{model_alias}',
                            new_status=StageStatus.PROCESSING,
                            celery_task_id=self.request.id
                        )
                        await session.flush()

                        source = await source_repo.get_by_id(uuid.UUID(source_id))
                        if not source:
                            raise ValueError(f"Source {source_id} not found")

                        # 2. Check idempotency
                        idem_key = get_idempotency_key(
                            uuid.UUID(tenant_id), uuid.UUID(source_id), 
                            "embed", model_alias
                        )

                        if await redis_client.exists(idem_key):
                            cached_data = await redis_client.get(idem_key)
                            try:
                                cached_json = json.loads(cached_data)
                                embeddings_key = cached_json.get("embeddings_key")
                                if embeddings_key and await s3_manager.object_exists(settings.S3_BUCKET_RAG, embeddings_key):
                                    logger.info(f"Embedding cached for {source_id}:{model_alias}")
                                    await status_manager.transition_stage(
                                        doc_id=uuid.UUID(source_id),
                                        stage=f'embed.{model_alias}',
                                        new_status=StageStatus.COMPLETED,
                                        metrics={'status': 'already_processed', 'cached': True}
                                    )
                                    await session.commit()
                                    return {
                                        "status": "already_processed", 
                                        "source_id": source_id, 
                                        "model_alias": model_alias,
                                        "embeddings_key": embeddings_key
                                    }
                            except Exception:
                                pass

                        # 3. Read Chunks
                        if not chunks_key:
                             # Try to find chunks_key via DB or S3 guess? No, fail fast.
                             raise ValueError(f"No chunks_key provided for source {source_id}")

                        chunks_content = await s3_manager.get_object(
                            bucket=settings.S3_BUCKET_RAG, 
                            key=chunks_key
                        )
                        # Parse JSONL
                        chunks = []
                        for line in chunks_content.decode('utf-8').splitlines():
                            if line.strip():
                                chunks.append(json.loads(line))
                        
                        if not chunks:
                             raise ValueError(f"No chunks found in file for {source_id}")

                        # 4. Prepare Embedding Service
                        embedding_service = EmbeddingServiceFactory.get_service(model_alias)
                        model_info = embedding_service.get_model_info()

                        # Update progress record
                        await emb_status_repo.create_or_update(
                            source_id=uuid.UUID(source_id),
                            model_alias=model_alias,
                            total_count=len(chunks),
                            model_version=model_info.version
                        )
                        await session.flush()

                        # 5. Generate Embeddings (Batch Processing)
                        batch_size = 32
                        embeddings_data = [] # List of dicts to save to JSONL
                        processed_count = 0

                        for i in range(0, len(chunks), batch_size):
                            batch_chunks = chunks[i:i + batch_size]
                            batch_texts = [c.get('text', '') for c in batch_chunks]

                            # Run sync embedding in thread
                            batch_vectors = await asyncio.to_thread(
                                embedding_service.embed_texts, 
                                batch_texts
                            )
                            
                            for chunk, vector in zip(batch_chunks, batch_vectors):
                                record = {
                                    "chunk_id": chunk['chunk_id'],
                                    "vector": vector,
                                    "index": chunk.get('index', 0)
                                }
                                embeddings_data.append(record)

                            processed_count += len(batch_chunks)
                            
                            # Update progress DB
                            await emb_status_repo.update_done_count(
                                uuid.UUID(source_id), 
                                model_alias, 
                                processed_count
                            )
                            
                            # Emit progress
                            from app.services.outbox_helper import emit_embed_progress
                            await emit_embed_progress(
                                session, repo_factory,
                                uuid.UUID(source_id),
                                model_alias,
                                done=processed_count,
                                total=len(chunks),
                                last_error=None
                            )
                            await session.flush()

                        # 6. Save Embeddings to S3
                        # We save them as JSONL: {"chunk_id": "...", "vector": [...]}
                        # This file will be read by Index task
                        embeddings_jsonl = "\n".join(json.dumps(e, ensure_ascii=False) for e in embeddings_data)
                        embeddings_checksum = calculate_text_checksum(str(len(embeddings_data)) + model_alias)
                        
                        embeddings_key = get_embeddings_path(
                            uuid.UUID(tenant_id), uuid.UUID(source_id), model_alias, embeddings_checksum, "v1", 0
                        ).replace('.npy', '.jsonl') # Force jsonl extension override
                        
                        await s3_manager.upload_content_sync(
                            bucket=settings.S3_BUCKET_RAG,
                            key=embeddings_key,
                            content=embeddings_jsonl.encode('utf-8'),
                            content_type="application/x-ndjson"
                        )

                        # 7. Complete
                        duration_sec = round(time.monotonic() - start_time, 2)
                        await status_manager.transition_stage(
                            doc_id=uuid.UUID(source_id),
                            stage=f'embed.{model_alias}',
                            new_status=StageStatus.COMPLETED,
                            metrics={
                                'vectors': len(embeddings_data),
                                'model_version': model_info.version,
                                'dimensions': model_info.dimensions,
                                'duration_sec': duration_sec,
                                'vectors_per_sec': round(len(embeddings_data) / duration_sec, 1) if duration_sec > 0 else 0
                            }
                        )
                        
                        # Emit final 100% progress
                        from app.services.outbox_helper import emit_embed_progress
                        await emit_embed_progress(
                            session, repo_factory,
                            uuid.UUID(source_id),
                            model_alias,
                            done=len(chunks),
                            total=len(chunks),
                            last_error=None
                        )
                        await session.flush()
                        
                        await redis_client.setex(
                            idem_key,
                            86400,
                            json.dumps({
                                "status": "completed", 
                                "embeddings_key": embeddings_key,
                                "count": len(embeddings_data)
                            })
                        )
                        
                        await session.commit()
                        
                        return {
                            "source_id": source_id,
                            "model_alias": model_alias,
                            "embeddings_key": embeddings_key,
                            "count": len(embeddings_data),
                            "status": "completed"
                        }

            except Exception as e:
                logger.error(f"Error in embed task for {source_id}:{model_alias}: {e}")
                try:
                    await notify_embed_error(source_id, tenant_id, model_alias, e)
                except Exception:
                    pass
                raise
            finally:
                if redis_client:
                    try:
                        await redis_client.close()
                        await redis_client.connection_pool.disconnect()
                    except Exception:
                        pass

        return asyncio.run(_embed())

    except Exception as e:
        logger.error(f"Error in embed_chunks_model for {source_id}: {e}")
        # No auto-retry - error is already handled in _embed() via notify_embed_error
        raise
