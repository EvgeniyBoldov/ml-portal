from __future__ import annotations
import logging
import uuid
from typing import Optional

from app.repositories.factory import AsyncRepositoryFactory
from app.services.rag_status_manager import RAGStatusManager, StageStatus
from app.services.rag_event_publisher import RAGEventPublisher

logger = logging.getLogger(__name__)


async def notify_stage_error(source_id: str, tenant_id: str, stage: str, error: Exception) -> None:
    """
    Notify status manager about task failure for a specific stage.
    This helper encapsulates session/redis/publisher setup for reuse across tasks.
    """
    try:
        from app.workers.session_factory import get_worker_session
        from app.core.config import get_settings
        import redis.asyncio as redis

        settings = get_settings()

        async with get_worker_session() as session:
            repo_factory = AsyncRepositoryFactory(session, uuid.UUID(tenant_id))

            redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
            event_publisher = RAGEventPublisher(redis_client)
            status_manager = RAGStatusManager(session, repo_factory, event_publisher)

            await status_manager.transition_stage(
                doc_id=uuid.UUID(source_id),
                stage=stage,
                new_status=StageStatus.FAILED,
                error=str(error)[:500],  # limit error size
            )
            await session.flush()  # Flush error status
    except Exception as notify_error:
        logger.error(f"notify_stage_error failed for {source_id}:{stage}: {notify_error}")


async def notify_embed_error(source_id: str, tenant_id: str, model_alias: str, error: Exception) -> None:
    """
    Notify about embed error and emit progress snapshot for the model.
    """
    try:
        from app.workers.session_factory import get_worker_session
        from app.core.config import get_settings
        import redis.asyncio as redis
        from app.repositories.factory import AsyncRepositoryFactory
        from app.services.rag_event_publisher import RAGEventPublisher
        from app.services.rag_status_manager import RAGStatusManager, StageStatus

        from app.repositories.rag_ingest_repos import AsyncEmbStatusRepository
        from app.services.outbox_helper import emit_embed_progress
        import uuid as _uuid

        settings = get_settings()

        async with get_worker_session() as session:
            repo_factory = AsyncRepositoryFactory(session, _uuid.UUID(tenant_id))

            redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)
            event_publisher = RAGEventPublisher(redis_client)
            status_manager = RAGStatusManager(session, repo_factory, event_publisher)

            # Mark stage failed
            await status_manager.transition_stage(
                doc_id=_uuid.UUID(source_id),
                stage=f'embed.{model_alias}',
                new_status=StageStatus.FAILED,
                error=str(error)[:500],
            )

            # Emit current progress snapshot
            emb_status_repo = AsyncEmbStatusRepository(session, _uuid.UUID(tenant_id))
            emb_status = await emb_status_repo.get_by_source_and_model(_uuid.UUID(source_id), model_alias)
            done = emb_status.done_count if emb_status else 0
            total = emb_status.total_count if emb_status else 0

            await emit_embed_progress(
                session, repo_factory,
                _uuid.UUID(source_id),
                model_alias,
                done=done,
                total=total,
                last_error=str(error),
            )

            await session.flush()  # Flush error status
    except Exception as notify_error:
        logger.error(f"notify_embed_error failed for {source_id}:{model_alias}: {notify_error}")
