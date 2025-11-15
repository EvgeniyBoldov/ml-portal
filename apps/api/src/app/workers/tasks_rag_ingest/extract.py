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
    get_idempotency_key,
)
from app.repositories.rag_ingest_repos import AsyncSourceRepository
from app.repositories.factory import AsyncRepositoryFactory
from app.services.rag_status_manager import RAGStatusManager, StageStatus
from app.services.rag_event_publisher import RAGEventPublisher
from app.workers.tasks_rag_ingest.error_utils import notify_stage_error

logger = logging.getLogger(__name__)


@celery_app.task(
    queue="ingest.extract",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=5
)
def extract_document(self: Task, source_id: str, tenant_id: str) -> Dict[str, Any]:
    """
    Extract text from document

    Args:
        source_id: Source ID to process
        tenant_id: Tenant ID

    Returns:
        Dict: Extraction result with raw text
    """
    logger.info(f"Starting extract_document for source_id: {source_id}")

    try:
        import asyncio
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
        
        async def _process():
            # Create engine and session factory for this event loop
            # This ensures engine is bound to the current event loop
            from app.core.config import get_settings
            settings = get_settings()
            
            # Create new engine for this event loop
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
                    # Initialize repositories and status manager
                    repo_factory = AsyncRepositoryFactory(session, uuid.UUID(tenant_id))
                    
                    # Get Redis client for event publishing
                    import redis.asyncio as redis
                    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
                    event_publisher = RAGEventPublisher(redis_client)
                    status_manager = RAGStatusManager(session, repo_factory, event_publisher)
                    
                    # Mark extract stage as processing
                    await status_manager.transition_stage(
                        doc_id=uuid.UUID(source_id),
                        stage='extract',
                        new_status=StageStatus.PROCESSING,
                        celery_task_id=self.request.id
                    )
                    await session.flush()  # Flush for SSE
                    
                    source_repo = AsyncSourceRepository(session, uuid.UUID(tenant_id))

                    # Get source
                    source = await source_repo.get_by_id(uuid.UUID(source_id))
                    if not source:
                        raise ValueError(f"Source {source_id} not found")

                    # Check idempotency
                    idem_key = get_idempotency_key(
                        uuid.UUID(tenant_id), uuid.UUID(source_id), 
                        "extract"
                    )

                    # Idempotency check using async Redis client
                    if await redis_client.exists(idem_key):
                        logger.info(f"Extract already completed for {source_id}")
                        # Still need to return canonical_key for chunk stage
                        # Find the canonical file that was already uploaded by listing objects
                        from app.storage.paths import get_document_prefix
                        prefix = get_document_prefix(uuid.UUID(tenant_id), uuid.UUID(source_id))
                        canonical_prefix = f"{prefix}/canonical/"
                        
                        # List objects to find the canonical file
                        objects = await s3_manager.list_objects(
                            bucket=get_settings().S3_BUCKET_RAG,
                            prefix=canonical_prefix
                        )
                        
                        if not objects:
                            raise ValueError(f"No canonical file found for {source_id}")
                        
                        # Use the first canonical file found
                        canonical_key = objects[0]['Key']
                        
                        # Mark extract stage as completed (already processed)
                        await status_manager.transition_stage(
                            doc_id=uuid.UUID(source_id),
                            stage='extract',
                            new_status=StageStatus.COMPLETED,
                            metrics={'status': 'already_processed', 'cached': True}
                        )
                        await session.flush()  # Flush for SSE
                        
                        return {
                            "status": "already_processed", 
                            "source_id": source_id,
                            "canonical_key": canonical_key
                        }

                    # Read file content from MinIO
                    origin_key = source.meta.get('s3_key')  # Changed from 'origin_key' to 's3_key'
                    if not origin_key:
                        raise ValueError(f"No s3_key found for source {source_id}")

                    file_content = await s3_manager.get_object(
                        bucket=get_settings().S3_BUCKET_RAG, 
                        key=origin_key
                    )

                    # Extract text using appropriate extractor based on file type
                    from app.services.text_extractor import extract_text
                    filename = source.meta.get('filename', '') or origin_key.split('/')[-1]
                    extract_result = extract_text(file_content, filename)
                    extracted_text = extract_result.text.strip()
                    
                    if extract_result.warnings:
                        logger.warning(f"Extraction warnings for {source_id}: {extract_result.warnings}")
                    
                    if not extracted_text:
                        raise ValueError(f"Failed to extract text from {filename}. Warnings: {extract_result.warnings}")

                    # Do not update Source.status here; it remains 'uploaded' until normalize completes
                    
                    # Mark extract stage as completed
                    metrics = {
                        'word_count': len(extracted_text.split()), 
                        'char_count': len(extracted_text),
                        'extractor': extract_result.kind,
                        'warnings_count': len(extract_result.warnings)
                    }
                    if extract_result.meta:
                        metrics.update(extract_result.meta)
                    
                    await status_manager.transition_stage(
                        doc_id=uuid.UUID(source_id),
                        stage='extract',
                        new_status=StageStatus.COMPLETED,
                        metrics=metrics
                    )
                    
                    await session.flush()  # Flush for SSE  # Commit the status update

                    # Store idempotency result
                    await redis_client.setex(idem_key, 86400, json.dumps({"status": "completed", "text_length": len(extracted_text)}))

                    return {
                        "source_id": source_id,
                        "extracted_text": extracted_text,
                        "status": "completed"
                    }
            finally:
                # Dispose engine after use
                await engine.dispose()

        return asyncio.run(_process())

    except Exception as e:
        logger.error(f"Error in extract_document for {source_id}: {e}")
        import asyncio
        try:
            asyncio.run(notify_stage_error(source_id, tenant_id, 'extract', e))
        except Exception as notify_error:
            logger.error(f"Failed to notify status router about error: {notify_error}")
        raise self.retry(exc=e, countdown=60, max_retries=3)
