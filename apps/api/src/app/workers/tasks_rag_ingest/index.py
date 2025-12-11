from __future__ import annotations
import logging
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
from app.storage.paths import get_idempotency_key
from app.repositories.rag_ingest_repos import AsyncChunkRepository, AsyncSourceRepository
from app.repositories.factory import AsyncRepositoryFactory
from app.services.rag_status_manager import RAGStatusManager, StageStatus
from app.services.rag_event_publisher import RAGEventPublisher
from app.workers.tasks_rag_ingest.error_utils import notify_stage_error
from app.workers.session_factory import get_worker_session_factory

logger = logging.getLogger(__name__)


@celery_app.task(
    queue="ingest.index",
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
)
def index_model(self: Task, embed_result: Dict[str, Any], tenant_id: str) -> Dict[str, Any]:
    """
    Index embeddings into Qdrant vector store.
    
    Flow:
    1. Read embeddings from S3 (embeddings.jsonl)
    2. Fetch chunk metadata from DB (Postgres)
    3. Upsert payload + vectors to Qdrant
    
    Args:
        embed_result: Result from embed_chunks_model task
        tenant_id: Tenant ID
    
    Returns:
        Dict: Index result
    """
    source_id = embed_result.get('source_id')
    model_alias = embed_result.get('model_alias')
    embeddings_key = embed_result.get('embeddings_key')
    
    logger.info(f"Starting index_model for source_id: {source_id}, model: {model_alias}")
    
    try:
        import asyncio
        
        async def _index():
            start_time = time.monotonic()
            settings = get_settings()
            session_factory = get_worker_session_factory()
            
            import redis.asyncio as redis
            redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
            
            lock_key = f"lock:index:{source_id}:{model_alias}"
            
            try:
                async with redis_client.lock(lock_key, timeout=600, blocking_timeout=5):
                    async with session_factory() as session:
                        repo_factory = AsyncRepositoryFactory(session, uuid.UUID(tenant_id))
                        event_publisher = RAGEventPublisher(redis_client)
                        status_manager = RAGStatusManager(session, repo_factory, event_publisher)
                        
                        chunk_repo = AsyncChunkRepository(session, uuid.UUID(tenant_id))
                        
                        # 1. Update status
                        await status_manager.transition_stage(
                            doc_id=uuid.UUID(source_id),
                            stage=f'index.{model_alias}',
                            new_status=StageStatus.PROCESSING,
                            celery_task_id=self.request.id
                        )
                        await session.flush()
                        
                        # 2. Check idempotency
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
                            await session.commit()
                            return {
                                "status": "already_processed", 
                                "source_id": source_id, 
                                "model_alias": model_alias
                            }
                        
                        # 3. Read Embeddings from S3 (Stream optimized)
                        if not embeddings_key:
                            raise ValueError(f"No embeddings_key provided for {source_id}")

                        # Use temporary file to avoid loading huge JSONL into memory
                        import tempfile
                        import os
                        
                        indexed_count = 0
                        
                        # 4. Fetch Chunks Metadata from DB
                        # Loading all chunks metadata might still be heavy if millions of chunks,
                        # but usually chunks metadata is much smaller than vectors.
                        # If this becomes a bottleneck, we'd need to paginate chunk fetching too.
                        chunks = await chunk_repo.get_by_source_id(uuid.UUID(source_id))
                        chunk_map = {c.chunk_id: c for c in chunks}
                        
                        # 5. Prepare Qdrant Client
                        from app.adapters.impl.qdrant import QdrantVectorStore
                        vector_store = QdrantVectorStore()
                        embedding_service = EmbeddingServiceFactory.get_service(model_alias)
                        model_info = embedding_service.get_model_info()
                        
                        collection_name = f"{tenant_id}__{model_alias}"
                        await vector_store.ensure_collection(collection_name, model_info.dimensions)

                        # Create temp file
                        fd, tmp_path = tempfile.mkstemp()
                        os.close(fd)
                        
                        try:
                            # Download to temp file
                            await s3_manager.download_file(
                                bucket=settings.S3_BUCKET_RAG, 
                                key=embeddings_key,
                                file_path=tmp_path
                            )
                            
                            # Read line by line and batch upsert
                            batch_size = 100
                            vectors = []
                            payloads = []
                            ids = []
                            
                            with open(tmp_path, 'r', encoding='utf-8') as f:
                                for line in f:
                                    line = line.strip()
                                    if not line:
                                        continue
                                        
                                    try:
                                        record = json.loads(line)
                                        chunk_id = record['chunk_id']
                                        chunk = chunk_map.get(chunk_id)
                                        
                                        if not chunk:
                                            # Chunk deleted or not found? Skip
                                            continue
                                            
                                        vectors.append(record['vector'])
                                        ids.append(str(uuid.uuid4())) # Qdrant Point ID
                                        
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
                                        
                                        # Upsert batch if full
                                        if len(vectors) >= batch_size:
                                            await vector_store.upsert(collection_name, vectors, payloads, ids)
                                            indexed_count += len(vectors)
                                            vectors = []
                                            payloads = []
                                            ids = []
                                            
                                    except json.JSONDecodeError:
                                        logger.warning(f"Skipping invalid JSON line in embeddings for {source_id}")
                                        continue
                            
                            # Upsert remaining
                            if vectors:
                                await vector_store.upsert(collection_name, vectors, payloads, ids)
                                indexed_count += len(vectors)
                                
                        finally:
                            # Cleanup temp file
                            if os.path.exists(tmp_path):
                                os.unlink(tmp_path)
                        
                        # 6. Handle empty case
                        if indexed_count == 0:
                             logger.warning(f"No embeddings indexed for {source_id}")
                             # Mark as done but empty
                             await status_manager.transition_stage(
                                doc_id=uuid.UUID(source_id),
                                stage=f'index.{model_alias}',
                                new_status=StageStatus.COMPLETED,
                                metrics={'indexed_count': 0}
                            )
                             await session.commit()
                             return {"status": "completed", "indexed_count": 0}

                        # 7. Complete
                        duration_sec = round(time.monotonic() - start_time, 2)
                        await status_manager.transition_stage(
                            doc_id=uuid.UUID(source_id),
                            stage=f'index.{model_alias}',
                            new_status=StageStatus.COMPLETED,
                            metrics={
                                'indexed_count': indexed_count,
                                'collection': collection_name,
                                'model_version': model_info.version,
                                'duration_sec': duration_sec
                            }
                        )
                        
                        await redis_client.setex(
                            idem_key,
                            86400,
                            json.dumps({"status": "completed", "indexed_count": indexed_count})
                        )
                        
                        await session.commit()
                        
                        # Trigger commit check via separate task if needed, 
                        # but RAGStatusManager updates aggregate status automatically.
                        
                        return {
                            "source_id": source_id,
                            "model_alias": model_alias,
                            "indexed_count": indexed_count,
                            "status": "completed"
                        }
            except Exception as e:
                logger.error(f"Error in index task for {source_id}:{model_alias}: {e}")
                try:
                    await notify_stage_error(source_id, tenant_id, f'index.{model_alias}', e)
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

        return asyncio.run(_index())
    
    except Exception as e:
        logger.error(f"Error in index_model for {source_id}: {e}")
        # No auto-retry - error is already handled in _index() via notify_stage_error
        raise


@celery_app.task(
    queue="ingest.commit",
    bind=True
)
def commit_source(self: Task, *args, **kwargs):
    # Placeholder to keep imports valid if referenced elsewhere, 
    # but main logic is now in status manager aggregation.
    pass
