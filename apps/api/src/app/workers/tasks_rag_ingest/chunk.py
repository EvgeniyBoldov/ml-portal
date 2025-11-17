from __future__ import annotations
import logging
import uuid
import json
import hashlib
from typing import Dict, Any
 

from celery import Task

from app.celery_app import app as celery_app
from app.core.config import get_settings
from app.adapters.s3_client import s3_manager
from app.storage.paths import (
    get_chunks_path,
    get_idempotency_key
)
from app.workers.helpers import chunker, generate_chunk_id
from app.repositories.rag_ingest_repos import AsyncSourceRepository, AsyncChunkRepository, AsyncEmbStatusRepository, AsyncModelRegistryRepository
from app.repositories.factory import AsyncRepositoryFactory
from app.services.rag_status_manager import RAGStatusManager, StageStatus
from app.services.rag_event_publisher import RAGEventPublisher
from app.workers.tasks_rag_ingest.error_utils import notify_stage_error

logger = logging.getLogger(__name__)


@celery_app.task(
    queue="ingest.chunk",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_backoff_max=600,
    max_retries=5
)
def chunk_document(self: Task, normalize_result: Dict[str, Any], tenant_id: str, chunk_profile: str = "by_tokens") -> Dict[str, Any]:
    """
    Chunk document into smaller pieces

    Args:
        normalize_result: Result from normalize_document task
        tenant_id: Tenant ID
        chunk_profile: Chunking profile

    Returns:
        Dict: Chunking result
    """
    # Extract source_id from previous task result
    if isinstance(normalize_result, dict) and 'source_id' in normalize_result:
        source_id = normalize_result['source_id']
    else:
        # Fallback for direct calls
        source_id = str(normalize_result)
    
    logger.info(f"Starting chunk_document for source_id: {source_id}")

    try:
        import asyncio

        async def _chunk():
            # Create engine and session factory inside async function
            # This ensures engine is bound to the correct event loop (asyncio.run creates new loop)
            from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
            from app.core.config import get_settings
            
            settings = get_settings()
            engine = create_async_engine(
                settings.ASYNC_DB_URL,
                echo=False,
                pool_pre_ping=True,
                pool_recycle=300,
                pool_size=2,  # Small pool for single task
                max_overflow=5,
            )
            session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
            
            try:
                async with session_factory() as session:
                    # Initialize repositories and status manager
                    repo_factory = AsyncRepositoryFactory(session, uuid.UUID(tenant_id))
                    
                    # Get Redis client for event publishing
                    import redis.asyncio as redis
                    redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
                    event_publisher = RAGEventPublisher(redis_client)
                    status_manager = RAGStatusManager(session, repo_factory, event_publisher)
                    
                    # Mark chunk stage as processing
                    await status_manager.transition_stage(
                        doc_id=uuid.UUID(source_id),
                        stage='chunk',
                        new_status=StageStatus.PROCESSING,
                        celery_task_id=self.request.id
                    )
                    await session.flush()  # Trigger SSE
                    
                    source_repo = AsyncSourceRepository(session, uuid.UUID(tenant_id))
                    chunk_repo = AsyncChunkRepository(session, uuid.UUID(tenant_id))
                    emb_status_repo = AsyncEmbStatusRepository(session, uuid.UUID(tenant_id))
                    model_registry_repo = AsyncModelRegistryRepository(session, uuid.UUID(tenant_id))

                    # Read canonical document from normalize result
                    canonical_key = normalize_result.get('canonical_key')
                    if not canonical_key:
                        raise ValueError(f"No canonical_key found in normalize result: {normalize_result}")
                    
                    canonical_content = await s3_manager.get_object(
                        bucket=get_settings().S3_BUCKET_RAG, 
                        key=canonical_key
                    )
                    canonical_doc = json.loads(canonical_content.decode('utf-8'))

                    # Check idempotency
                    content_hash = hashlib.sha256(canonical_doc["text"].encode()).hexdigest()
                    idem_key = get_idempotency_key(
                        uuid.UUID(tenant_id), uuid.UUID(source_id), 
                        "chunk", content_hash=content_hash
                    )

                    # Use async redis client created above
                    if await redis_client.exists(idem_key):
                        logger.info(f"Chunking already completed for {source_id}")
                        # Mark chunk stage as completed (cached)
                        await status_manager.transition_stage(
                            doc_id=uuid.UUID(source_id),
                            stage='chunk',
                            new_status=StageStatus.COMPLETED,
                            metrics={'status': 'already_processed', 'cached': True}
                        )
                        await session.flush()  # Trigger SSE
                        await session.commit()  # Commit before return
                        return {"status": "already_processed", "source_id": source_id}

                    # Chunk the text
                    chunks_data = chunker(
                        canonical_doc["text"], 
                        chunk_profile,
                        chunk_size=512,
                        overlap=50
                    )

                    # Generate chunks with IDs
                    chunks = []
                    for i, chunk_data in enumerate(chunks_data):
                        chunk_id = generate_chunk_id(uuid.UUID(source_id), chunk_data["start_pos"], chunk_data["end_pos"])
                        chunk = {
                            "chunk_id": chunk_id,
                            "source_id": source_id,
                            "offset": chunk_data["start_pos"],
                            "length": chunk_data["end_pos"] - chunk_data["start_pos"],
                            "page": chunk_data.get("page"),
                            "lang": canonical_doc["metadata"].get("language"),
                            "hash": hashlib.sha256(chunk_data["text"].encode()).hexdigest(),
                            "meta": {
                                "text": chunk_data["text"],
                                "word_count": chunk_data["word_count"],
                                "char_count": chunk_data["char_count"],
                                "chunk_index": i,
                                "profile": chunk_profile,
                                "start_pos": chunk_data["start_pos"],
                                "end_pos": chunk_data["end_pos"]
                            }
                        }
                        chunks.append(chunk)

                # Save chunks to database
                    await chunk_repo.bulk_upsert(chunks)
                    await session.flush()  # Flush chunks to DB

                # Calculate checksum for chunks content
                    from app.storage.paths import calculate_text_checksum
                    chunks_content = "\n".join(json.dumps(chunk, ensure_ascii=False) for chunk in chunks)
                    chunks_checksum = calculate_text_checksum(chunks_content)
                
                # Save chunks manifest with checksum
                    chunks_manifest_key = get_chunks_path(
                    uuid.UUID(tenant_id), uuid.UUID(source_id), chunks_checksum, "v1"
                    )
                    await s3_manager.upload_content_sync(
                        bucket=get_settings().S3_BUCKET_RAG,
                        key=chunks_manifest_key,
                        content=chunks_content.encode('utf-8'),
                        content_type="application/jsonl"
                    )

                # Mark chunk stage as completed
                    await status_manager.transition_stage(
                        doc_id=uuid.UUID(source_id),
                        stage='chunk',
                        new_status=StageStatus.COMPLETED,
                        metrics={
                            'chunks_count': len(chunks),
                            'avg_chunk_size': sum(c['length'] for c in chunks) // len(chunks) if chunks else 0,
                            'profile': chunk_profile
                        }
                    )
                
                # Create EmbStatus entries for all models and emit initial progress
                    from app.core.config import get_embedding_models
                    from app.services.outbox_helper import emit_embed_progress
                    embedding_models = get_embedding_models()
                
                    for model_alias in embedding_models:
                        model_registry = await model_registry_repo.get_by_alias(model_alias)
                        if model_registry:
                            await emb_status_repo.create_or_update(
                                uuid.UUID(source_id), 
                                model_alias, 
                                len(chunks),
                                model_registry.version
                            )
                            # Emit initial embed progress event (0 done, total chunks)
                            await emit_embed_progress(
                                session, repo_factory,
                                uuid.UUID(source_id),
                                model_alias,
                                done=0,
                                total=len(chunks),
                                last_error=None
                            )
                
                    await session.flush()  # Trigger SSE + outbox events

                    # Store idempotency result
                    await redis_client.setex(idem_key, 86400, json.dumps({"status": "completed", "chunks_count": len(chunks)}))
                    
                    await session.commit()  # Final commit

                    return {
                        "source_id": source_id,
                        "chunks_manifest_key": chunks_manifest_key,
                        "total_chunks": len(chunks),
                        "status": "completed"
                    }
            finally:
                # Dispose engine when done (important for event loop lifecycle)
                await engine.dispose()

        return asyncio.run(_chunk())

    except Exception as e:
        logger.error(f"Error in chunk_document for {source_id}: {e}")
        import asyncio
        try:
            asyncio.run(notify_stage_error(source_id, tenant_id, 'chunk', e))
        except Exception as notify_error:
            logger.error(f"Failed to notify status router about error: {notify_error}")
        raise self.retry(exc=e, countdown=60, max_retries=3)

