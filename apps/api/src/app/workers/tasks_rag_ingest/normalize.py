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
from app.storage.paths import (
    get_canonical_path,
    get_idempotency_key,
)
from app.repositories.rag_ingest_repos import AsyncSourceRepository
from app.repositories.factory import AsyncRepositoryFactory
from app.services.rag_status_manager import RAGStatusManager, StageStatus
from app.services.rag_event_publisher import RAGEventPublisher
from app.workers.tasks_rag_ingest.error_utils import notify_stage_error

logger = logging.getLogger(__name__)

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
    Normalize extracted text into canonical JSON format
    
    Args:
        extract_result: Result from extract_document task
        tenant_id: Tenant ID
    
    Returns:
        Dict: Normalization result with canonical_key
    """
    source_id = extract_result.get('source_id')
    extracted_text = extract_result.get('extracted_text', '')
    
    logger.info(f"Starting normalize_document for source_id: {source_id}")
    
    try:
        import asyncio
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        
        async def _normalize():
            from app.core.config import get_settings
            settings = get_settings()
            
            engine = create_async_engine(
                settings.ASYNC_DB_URL,
                echo=False,
                pool_pre_ping=True,
                pool_recycle=300,
                pool_size=2,
                max_overflow=5,
            )
            session_factory = async_sessionmaker(engine, expire_on_commit=False)
            
            try:
                async with session_factory() as session:
                    repo_factory = AsyncRepositoryFactory(session, uuid.UUID(tenant_id))
                    
                    import redis.asyncio as redis
                    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
                    event_publisher = RAGEventPublisher(redis_client)
                    status_manager = RAGStatusManager(session, repo_factory, event_publisher)
                    
                    source_repo = AsyncSourceRepository(session, uuid.UUID(tenant_id))
                    
                    # Mark normalize stage as processing
                    await status_manager.transition_stage(
                        doc_id=uuid.UUID(source_id),
                        stage='normalize',
                        new_status=StageStatus.PROCESSING,
                        celery_task_id=self.request.id
                    )
                    await session.commit()
                    
                    # Check idempotency
                    idem_key = get_idempotency_key(
                        uuid.UUID(tenant_id), uuid.UUID(source_id), 
                        "normalize"
                    )
                    
                    if await redis_client.exists(idem_key):
                        logger.info(f"Normalize already completed for {source_id}")
                        # Try to find existing canonical file
                        from app.storage.paths import get_document_prefix
                        prefix = get_document_prefix(uuid.UUID(tenant_id), uuid.UUID(source_id))
                        canonical_prefix = f"{prefix}/canonical/"
                        
                        objects = await s3_manager.list_objects(
                            bucket=settings.S3_BUCKET_RAG,
                            prefix=canonical_prefix
                        )
                        
                        if objects:
                            canonical_key = objects[0]['Key']
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
                        
                        # Canonical missing despite idempotency key: regenerate from extracted_text
                        logger.warning(f"Idempotency key exists but no canonical file for {source_id}. Regenerating.")
                        source = await source_repo.get_by_id(uuid.UUID(source_id))
                        if not source:
                            raise ValueError(f"Source {source_id} not found")
                        
                        from app.storage.paths import calculate_text_checksum
                        content_checksum = calculate_text_checksum(extracted_text)
                        canonical_key = get_canonical_path(
                            uuid.UUID(tenant_id), uuid.UUID(source_id), content_checksum, "v1"
                        )
                        canonical_doc = {
                            "source_id": source_id,
                            "tenant_id": tenant_id,
                            "text": extracted_text,
                            "metadata": {
                                "language": "en",
                                "word_count": len(extracted_text.split()),
                                "char_count": len(extracted_text),
                                "mime_type": source.meta.get('mime_type', 'text/plain'),
                                "version": "v1"
                            },
                            "created_at": datetime.now(timezone.utc).isoformat()
                        }
                        canonical_content = json.dumps(canonical_doc, ensure_ascii=False)
                        await s3_manager.upload_content_sync(
                            bucket=settings.S3_BUCKET_RAG,
                            key=canonical_key,
                            content=canonical_content.encode('utf-8'),
                            content_type="application/jsonl"
                        )
                        await status_manager.transition_stage(
                            doc_id=uuid.UUID(source_id),
                            stage='normalize',
                            new_status=StageStatus.COMPLETED,
                            metrics={'status': 'recreated_from_cache', 'cached': True}
                        )
                        await session.commit()
                        return {
                            "status": "recreated",
                            "source_id": source_id,
                            "canonical_key": canonical_key
                        }
                    
                    # Get source for metadata
                    source = await source_repo.get_by_id(uuid.UUID(source_id))
                    if not source:
                        raise ValueError(f"Source {source_id} not found")
                    
                    # Create canonical document
                    canonical_doc = {
                        "source_id": source_id,
                        "tenant_id": tenant_id,
                        "text": extracted_text,
                        "metadata": {
                            "language": "en",
                            "word_count": len(extracted_text.split()),
                            "char_count": len(extracted_text),
                            "mime_type": source.meta.get('mime_type', 'text/plain'),
                            "version": "v1"
                        },
                        "created_at": datetime.now(timezone.utc).isoformat()
                    }
                    
                    # Calculate checksum and save
                    from app.storage.paths import calculate_text_checksum
                    content_checksum = calculate_text_checksum(extracted_text)
                    
                    canonical_key = get_canonical_path(
                        uuid.UUID(tenant_id), uuid.UUID(source_id), content_checksum, "v1"
                    )
                    canonical_content = json.dumps(canonical_doc, ensure_ascii=False)
                    
                    await s3_manager.upload_content_sync(
                        bucket=settings.S3_BUCKET_RAG,
                        key=canonical_key,
                        content=canonical_content.encode('utf-8'),
                        content_type="application/jsonl"
                    )
                    
                    # Update source status
                    await source_repo.update_status(uuid.UUID(source_id), 'normalized')
                    
                    # Mark normalize stage as completed
                    await status_manager.transition_stage(
                        doc_id=uuid.UUID(source_id),
                        stage='normalize',
                        new_status=StageStatus.COMPLETED,
                        metrics={
                            'word_count': len(extracted_text.split()),
                            'char_count': len(extracted_text)
                        }
                    )
                    
                    await session.commit()
                    
                    # Store idempotency
                    await redis_client.setex(idem_key, 86400, json.dumps({"status": "completed"}))
                    
                    return {
                        "source_id": source_id,
                        "canonical_key": canonical_key,
                        "status": "completed"
                    }
            finally:
                await engine.dispose()
        
        return asyncio.run(_normalize())
    
    except Exception as e:
        logger.error(f"Error in normalize_document for {source_id}: {e}")
        import asyncio
        try:
            asyncio.run(notify_stage_error(source_id, tenant_id, 'normalize', e))
        except Exception as notify_error:
            logger.error(f"Failed to notify status router about error: {notify_error}")
        raise self.retry(exc=e, countdown=60, max_retries=3)
