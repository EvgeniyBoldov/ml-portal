from __future__ import annotations
from app.core.logging import get_logger
import uuid
import json
import time
from typing import Dict, Any, List
from datetime import datetime, timezone

from celery import Task

from app.celery_app import app as celery_app
from app.core.config import get_settings
from app.adapters.s3_client import s3_manager
from app.storage.paths import (
    get_idempotency_key,
    get_chunks_path,
    calculate_text_checksum
)
from app.repositories.rag_ingest_repos import AsyncSourceRepository, AsyncChunkRepository
from app.repositories.factory import AsyncRepositoryFactory
from app.services.rag_status_manager import RAGStatusManager, StageStatus
from app.services.rag_event_publisher import RAGEventPublisher
from app.workers.tasks_rag_ingest.error_utils import notify_stage_error
from app.workers.session_factory import get_worker_session
from app.workers.helpers import chunker, create_chunk_payload, generate_chunk_id
from app.schemas.common import ChunkProfile

logger = get_logger(__name__)


@celery_app.task(
    queue="ingest.chunk",
    bind=True,
    acks_late=True,
    reject_on_worker_lost=True,
)
def chunk_document(self: Task, normalize_result: Dict[str, Any], tenant_id: str) -> Dict[str, Any]:
    """
    Chunk document text.
    
    Flow:
    1. Read canonical document from S3
    2. Split text into chunks (smart chunking)
    3. Save chunks to Database (for management)
    4. Upload chunks dump to S3 (for efficient embedding iteration)
    5. Return path to chunks dump
    
    Args:
        normalize_result: Result from normalize_document task
        tenant_id: Tenant ID
    
    Returns:
        Dict: Chunking result with chunks_key (s3 path)
    """
    if isinstance(normalize_result, dict) and 'source_id' in normalize_result:
        source_id = normalize_result['source_id']
        canonical_key = normalize_result.get('canonical_key')
    else:
        source_id = str(normalize_result)
        canonical_key = None

    logger.info(f"Starting chunk_document for source_id: {source_id}")

    try:
        import asyncio
        
        async def _process():
            start_time = time.monotonic()
            settings = get_settings()
            
            redis_client = None
            try:
                async with get_worker_session() as session:
                    repo_factory = AsyncRepositoryFactory(session, uuid.UUID(tenant_id))
                    
                    import redis.asyncio as redis
                    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
                    event_publisher = RAGEventPublisher(redis_client)
                    status_manager = RAGStatusManager(session, repo_factory, event_publisher)
                    
                    # 1. Update status
                    await status_manager.transition_stage(
                        doc_id=uuid.UUID(source_id),
                        stage='chunk',
                        new_status=StageStatus.PROCESSING,
                        celery_task_id=self.request.id
                    )
                    await session.flush()
                    
                    source_repo = AsyncSourceRepository(session, uuid.UUID(tenant_id))
                    source = await source_repo.get_by_id(uuid.UUID(source_id))
                    if not source:
                        raise ValueError(f"Source {source_id} not found")

                    # 2. Check idempotency
                    idem_key = get_idempotency_key(
                        uuid.UUID(tenant_id), uuid.UUID(source_id), 
                        "chunk"
                    )

                    if await redis_client.exists(idem_key):
                        cached_data = await redis_client.get(idem_key)
                        try:
                            cached_json = json.loads(cached_data)
                            chunks_key = cached_json.get("chunks_key")
                            if chunks_key and await s3_manager.object_exists(settings.S3_BUCKET_RAG, chunks_key):
                                logger.info(f"Chunk cached for {source_id}")
                                await status_manager.transition_stage(
                                    doc_id=uuid.UUID(source_id),
                                    stage='chunk',
                                    new_status=StageStatus.COMPLETED,
                                    metrics={'status': 'already_processed', 'cached': True}
                                )
                                await session.commit()
                                return {
                                    "status": "already_processed", 
                                    "source_id": source_id,
                                    "chunks_key": chunks_key
                                }
                        except Exception:
                            pass

                    # 3. Read Canonical Document
                    if not canonical_key:
                         raise ValueError(f"No canonical_key provided for source {source_id}")

                    canonical_content = await s3_manager.get_object(
                        bucket=settings.S3_BUCKET_RAG, 
                        key=canonical_key
                    )
                    canonical_doc = json.loads(canonical_content)
                    text = canonical_doc.get("text", "")
                    
                    if not text:
                        logger.warning(f"Empty text in canonical doc for {source_id}")
                        # Create empty chunks list
                        chunks_data = []
                    else:
                        # 4. Chunking
                        profile = ChunkProfile.BY_TOKENS  # Default
                        chunk_size = 512
                        overlap = 50
                        
                        # Example: If source.meta has 'chunk_strategy'
                        if source.meta.get('chunk_strategy') == 'paragraphs':
                            profile = ChunkProfile.BY_PARAGRAPHS
                        
                        raw_chunks = chunker(
                            text, 
                            profile=profile, 
                            chunk_size=chunk_size, 
                            overlap=overlap
                        )
                        
                        # Format chunks
                        chunks_data = []
                        for i, rc in enumerate(raw_chunks):
                            chunk_id = generate_chunk_id(uuid.UUID(source_id), rc['start_pos'], rc['end_pos'])
                            payload = create_chunk_payload(
                                tenant_id=uuid.UUID(tenant_id),
                                document_id=uuid.UUID(source_id),
                                chunk_id=chunk_id,
                                text=rc['text'],
                                start_pos=rc['start_pos'],
                                end_pos=rc['end_pos'],
                                metadata=canonical_doc.get('metadata')
                            )
                            # Add index for ordering
                            payload['index'] = i
                            chunks_data.append(payload)

                    # 5. Save to DB (bulk insert)
                    # Delete old chunks first to ensure idempotency on DB level
                    chunk_repo = AsyncChunkRepository(session, uuid.UUID(tenant_id))
                    await chunk_repo.delete_by_document_id(uuid.UUID(source_id))
                    
                    if chunks_data:
                        # Use repository for batch insert
                        await chunk_repo.create_batch(chunks_data)

                    # 6. Upload Chunks Dump to S3 (JSONL)
                    # JSONL is better for streaming large datasets
                    chunks_jsonl = "\n".join(json.dumps(c, ensure_ascii=False) for c in chunks_data)
                    chunks_checksum = calculate_text_checksum(text + str(len(chunks_data))) # Simple checksum based on text+count
                    
                    chunks_key = get_chunks_path(
                        uuid.UUID(tenant_id), uuid.UUID(source_id), chunks_checksum
                    )
                    
                    await s3_manager.upload_content_sync(
                        bucket=settings.S3_BUCKET_RAG,
                        key=chunks_key,
                        content=chunks_jsonl.encode('utf-8'),
                        content_type="application/x-ndjson"
                    )

                    # Update Source meta with chunks_key for reindexing capability
                    if not source.meta:
                        source.meta = {}
                    # Create a copy to ensure SQLAlchemy tracks the change if it's a JSON field
                    new_meta = source.meta.copy()
                    new_meta['chunks_key'] = chunks_key
                    # We need to update via repository or assignment if attached
                    # source is attached to session
                    source.meta = new_meta
                    # Explicit update if needed, but session commit should catch it
                    
                    # 7. Complete
                    duration_sec = round(time.monotonic() - start_time, 2)
                    await status_manager.transition_stage(
                        doc_id=uuid.UUID(source_id),
                        stage='chunk',
                        new_status=StageStatus.COMPLETED,
                        metrics={
                            'chunk_count': len(chunks_data),
                            'strategy': str(profile),
                            'avg_chunk_size': round(sum(len(c['text']) for c in chunks_data) / len(chunks_data), 1) if chunks_data else 0,
                            'duration_sec': duration_sec
                        }
                    )
                    
                    await redis_client.setex(
                        idem_key, 
                        86400, 
                        json.dumps({
                            "status": "completed", 
                            "chunks_key": chunks_key,
                            "chunk_count": len(chunks_data)
                        })
                    )
                    
                    await session.commit()

                    return {
                        "source_id": source_id,
                        "chunks_key": chunks_key,
                        "chunk_count": len(chunks_data),
                        "status": "completed"
                    }
            except Exception as e:
                try:
                    await notify_stage_error(source_id, tenant_id, 'chunk', e)
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

        return asyncio.run(_process())

    except Exception as e:
        logger.error(f"Error in chunk_document for {source_id}: {e}")
        # No auto-retry - error is already handled in _process() via notify_stage_error
        raise
