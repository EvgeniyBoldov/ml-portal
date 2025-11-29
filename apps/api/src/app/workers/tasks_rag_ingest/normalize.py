from __future__ import annotations
import logging
import uuid
import json
import re
from typing import Dict, Any
from datetime import datetime, timezone

from celery import Task

from app.celery_app import app as celery_app
from app.core.config import get_settings
from app.adapters.s3_client import s3_manager
from app.storage.paths import (
    get_idempotency_key,
    get_canonical_path,
    calculate_text_checksum
)
from app.repositories.rag_ingest_repos import AsyncSourceRepository
from app.repositories.factory import AsyncRepositoryFactory
from app.services.rag_status_manager import RAGStatusManager, StageStatus
from app.services.rag_event_publisher import RAGEventPublisher
from app.workers.tasks_rag_ingest.error_utils import notify_stage_error
from app.workers.session_factory import get_worker_session_factory

logger = logging.getLogger(__name__)


def smart_normalize(text: str) -> str:
    """
    Normalize text while preserving structure (paragraphs).
    1. Remove control characters (except whitespace)
    2. Replace multiple horizontal spaces with single space
    3. Replace 3+ newlines with 2 newlines (paragraph break)
    4. Trim whitespace
    """
    if not text:
        return ""
        
    # 1. Remove non-printable chars (allow newlines/tabs)
    text = "".join(ch for ch in text if ch.isprintable() or ch in ['\n', '\t', '\r'])
    
    # 2. Replace windows line endings
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    
    # 3. Collapse horizontal whitespace (spaces, tabs) to single space
    # Note: This regex preserves newlines
    text = re.sub(r'[ \t]+', ' ', text)
    
    # 4. Collapse multiple newlines to max 2 (paragraph separator)
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()


@celery_app.task(
    queue="ingest.normalize",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=5
)
def normalize_document(self: Task, extract_result: Dict[str, Any], tenant_id: str) -> Dict[str, Any]:
    """
    Normalize text and convert to canonical format.
    
    Flow:
    1. Read extracted raw text from S3
    2. Normalize text (cleanup, unicode fix)
    3. Create canonical document structure (JSON)
    4. Upload canonical document to S3
    5. Return path to canonical document
    
    Args:
        extract_result: Result from extract_document task
        tenant_id: Tenant ID
    
    Returns:
        Dict: Normalize result with canonical_key (s3 path)
    """
    # Handle input flexibility (direct or from chain)
    if isinstance(extract_result, dict) and 'source_id' in extract_result:
        source_id = extract_result['source_id']
        extracted_key = extract_result.get('extracted_key')
    else:
        # Fallback (should not happen in new flow)
        source_id = str(extract_result)
        extracted_key = None
    
    logger.info(f"Starting normalize_document for source_id: {source_id}")

    try:
        import asyncio
        
        async def _process():
            settings = get_settings()
            session_factory = get_worker_session_factory()
            
            redis_client = None
            try:
                async with session_factory() as session:
                    repo_factory = AsyncRepositoryFactory(session, uuid.UUID(tenant_id))
                    
                    import redis.asyncio as redis
                    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
                    event_publisher = RAGEventPublisher(redis_client)
                    status_manager = RAGStatusManager(session, repo_factory, event_publisher)
                    
                    # 1. Update status
                    await status_manager.transition_stage(
                        doc_id=uuid.UUID(source_id),
                        stage='normalize',
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
                        "normalize"
                    )

                    if await redis_client.exists(idem_key):
                        cached_data = await redis_client.get(idem_key)
                        try:
                            cached_json = json.loads(cached_data)
                            canonical_key = cached_json.get("canonical_key")
                            if canonical_key and await s3_manager.object_exists(settings.S3_BUCKET_RAG, canonical_key):
                                logger.info(f"Normalize cached for {source_id}")
                                await status_manager.transition_stage(
                                    doc_id=uuid.UUID(source_id),
                                    stage='normalize',
                                    new_status=StageStatus.COMPLETED,
                                    metrics={'status': 'already_processed', 'cached': True}
                                )
                                await session.commit()
                                return {
                                    "status": "already_processed", 
                                    "source_id": source_id,
                                    "canonical_key": canonical_key
                                }
                        except Exception:
                            pass

                    # 3. Read Extracted Text
                    if not extracted_key:
                        # Try to find if not passed (fallback)
                        # In production this should fail, but for migration safety we might search
                        raise ValueError(f"No extracted_key provided for source {source_id}")
                        
                    extracted_content = await s3_manager.get_object(
                        bucket=settings.S3_BUCKET_RAG, 
                        key=extracted_key
                    )
                    raw_text = extracted_content.decode('utf-8')

                    # 4. Normalize
                    normalized_text = smart_normalize(raw_text)
                    
                    if not normalized_text:
                         # If empty after normalization, maybe it was only noise
                         logger.warning(f"Text became empty after normalization for {source_id}")
                         # We still proceed to create an empty canonical doc or fail?
                         # Better to have at least something.
                         normalized_text = ""

                    # 5. Create Canonical Document
                    # Canonical format: JSON with text and metadata
                    canonical_doc = {
                        "text": normalized_text,
                        "metadata": {
                            "source_id": source_id,
                            "tenant_id": tenant_id,
                            "filename": source.meta.get('filename'),
                            "title": source.title,
                            "language": source.meta.get('language', 'en'),
                            "created_at": datetime.now(timezone.utc).isoformat(),
                            "original_size": len(raw_text),
                            "normalized_size": len(normalized_text)
                        }
                    }
                    
                    canonical_content = json.dumps(canonical_doc, ensure_ascii=False)
                    
                    # 6. Upload Canonical
                    content_checksum = calculate_text_checksum(normalized_text)
                    canonical_key = get_canonical_path(
                        uuid.UUID(tenant_id), uuid.UUID(source_id), content_checksum
                    )
                    
                    await s3_manager.upload_content_sync(
                        bucket=settings.S3_BUCKET_RAG,
                        key=canonical_key,
                        content=canonical_content.encode('utf-8'),
                        content_type="application/json"
                    )
                    
                    # 7. Complete
                    await status_manager.transition_stage(
                        doc_id=uuid.UUID(source_id),
                        stage='normalize',
                        new_status=StageStatus.COMPLETED,
                        metrics={
                            'original_size': len(raw_text),
                            'normalized_size': len(normalized_text),
                            'reduction_ratio': round(1 - (len(normalized_text) / len(raw_text) if raw_text else 0), 2)
                        }
                    )
                    
                    await redis_client.setex(
                        idem_key, 
                        86400, 
                        json.dumps({
                            "status": "completed", 
                            "canonical_key": canonical_key,
                            "checksum": content_checksum
                        })
                    )
                    
                    await session.commit()

                    return {
                        "source_id": source_id,
                        "canonical_key": canonical_key,
                        "status": "completed"
                    }
            except Exception as e:
                try:
                    await notify_stage_error(source_id, tenant_id, 'normalize', e)
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
        logger.error(f"Error in normalize_document for {source_id}: {e}")
        raise self.retry(exc=e, countdown=60, max_retries=3)
