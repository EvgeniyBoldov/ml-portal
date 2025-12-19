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
from app.storage.paths import (
    get_idempotency_key,
    get_extracted_path,
    calculate_text_checksum
)
from app.repositories.rag_ingest_repos import AsyncSourceRepository
from app.repositories.factory import AsyncRepositoryFactory
from app.services.rag_status_manager import RAGStatusManager, StageStatus
from app.services.rag_event_publisher import RAGEventPublisher
from app.workers.tasks_rag_ingest.error_utils import notify_stage_error
from app.workers.session_factory import get_worker_session

logger = get_logger(__name__)


@celery_app.task(
    queue="ingest.extract",
    bind=True,
    acks_late=True,  # Acknowledge after task completes
    reject_on_worker_lost=True,  # Requeue if worker dies
)
def extract_document(self: Task, source_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Extract text from document.
    
    Flow:
    1. Download original file from S3
    2. Extract text (preserving structure if possible)
    3. Upload extracted raw text to S3
    4. Return path to extracted text
    
    Args:
        source_id: Source ID to process
        tenant_id: Tenant ID
    
    Returns:
        Dict: Extraction result with extracted_key (s3 path)
    """
    logger.info(f"Starting extract_document for source_id: {source_id}")

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
                        stage='extract',
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
                        "extract"
                    )

                    if await redis_client.exists(idem_key):
                        cached_data = await redis_client.get(idem_key)
                        try:
                            cached_json = json.loads(cached_data)
                            extracted_key = cached_json.get("extracted_key")
                            if extracted_key and await s3_manager.object_exists(settings.S3_BUCKET_RAG, extracted_key):
                                logger.info(f"Extract cached for {source_id}")
                                await status_manager.transition_stage(
                                    doc_id=uuid.UUID(source_id),
                                    stage='extract',
                                    new_status=StageStatus.COMPLETED,
                                    metrics={'status': 'already_processed', 'cached': True}
                                )
                                await session.commit()
                                return {
                                    "status": "already_processed", 
                                    "source_id": source_id,
                                    "extracted_key": extracted_key
                                }
                        except Exception:
                            logger.warning("Invalid cache for extract, reprocessing")

                    # 3. Download Original
                    origin_key = source.meta.get('s3_key')
                    if not origin_key:
                        raise ValueError(f"No s3_key found for source {source_id}")

                    file_content = await s3_manager.get_object(
                        bucket=settings.S3_BUCKET_RAG, 
                        key=origin_key
                    )

                    # 4. Extract Text
                    from app.services.text_extractor import extract_text
                    filename = source.meta.get('filename', '') or origin_key.split('/')[-1]
                    extract_result = extract_text(file_content, filename)
                    extracted_text = extract_result.text.strip()
                    
                    if not extracted_text:
                        raise ValueError(f"Failed to extract text from {filename}")

                    # 5. Upload Artifact
                    text_checksum = calculate_text_checksum(extracted_text)
                    extracted_key = get_extracted_path(
                        uuid.UUID(tenant_id), uuid.UUID(source_id), text_checksum
                    )
                    
                    await s3_manager.upload_content_sync(
                        bucket=settings.S3_BUCKET_RAG,
                        key=extracted_key,
                        content=extracted_text.encode('utf-8'),
                        content_type="text/plain"
                    )
                    
                    # 6. Complete
                    duration_sec = round(time.monotonic() - start_time, 2)
                    metrics = {
                        'word_count': len(extracted_text.split()), 
                        'char_count': len(extracted_text),
                        'extractor': extract_result.kind,
                        'checksum': text_checksum,
                        'duration_sec': duration_sec,
                        'file_size_bytes': len(file_content)
                    }
                    if extract_result.meta:
                        metrics.update(extract_result.meta)
                    
                    await status_manager.transition_stage(
                        doc_id=uuid.UUID(source_id),
                        stage='extract',
                        new_status=StageStatus.COMPLETED,
                        metrics=metrics
                    )
                    
                    await redis_client.setex(
                        idem_key, 
                        86400, 
                        json.dumps({
                            "status": "completed", 
                            "extracted_key": extracted_key,
                            "checksum": text_checksum
                        })
                    )
                    
                    await session.commit()

                    return {
                        "source_id": source_id,
                        "extracted_key": extracted_key,
                        "status": "completed"
                    }
            except Exception as e:
                try:
                    await notify_stage_error(source_id, tenant_id, 'extract', e)
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
        logger.error(f"Error in extract_document for {source_id}: {e}")
        # No auto-retry - error is already handled in _process() via notify_stage_error
        raise
