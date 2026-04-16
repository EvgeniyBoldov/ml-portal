"""
IngestStageContext — runtime context for a single RAG ingest stage.

Encapsulates the repeated boilerplate that every Celery task needs:
- AsyncSession (via get_worker_session)
- Redis client
- AsyncRepositoryFactory
- RAGEventPublisher
- RAGStatusManager
- Idempotency check helpers
- Error notification

Usage inside a Celery task:

    @celery_app.task(queue="ingest.extract", bind=True, acks_late=True, reject_on_worker_lost=True)
    def extract_document(self: Task, source_id: str, tenant_id: str) -> Dict[str, Any]:
        def _execute(ctx: IngestStageContext) -> ExtractResult:
            # pure business logic here — ctx gives you everything
            ...
            return ExtractResult(source_id=source_id, extracted_key=key)

        return run_stage(
            stage_name="extract",
            source_id=source_id,
            tenant_id=tenant_id,
            celery_task=self,
            execute_fn=_execute,
        )
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import (
    Any,
    AsyncGenerator,
    Awaitable,
    Callable,
    Dict,
    Optional,
    TypeVar,
)

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.s3_client import s3_manager
from app.core.config import get_settings
from app.core.logging import get_logger
from app.repositories.factory import AsyncRepositoryFactory
from app.services.rag_event_publisher import RAGEventPublisher
from app.services.rag_status_manager import RAGStatusManager, StageStatus
from app.storage.paths import get_idempotency_key
from app.workers.session_factory import get_worker_session
from app.workers.tasks_rag_ingest.error_utils import notify_stage_error

logger = get_logger(__name__)

T = TypeVar("T")


@dataclass
class IngestStageContext:
    """Runtime context available to every ingest stage."""

    source_id: uuid.UUID
    tenant_id: uuid.UUID
    stage_name: str

    session: AsyncSession
    redis: aioredis.Redis
    settings: Any  # app Settings object

    repo_factory: AsyncRepositoryFactory
    event_publisher: RAGEventPublisher
    status_manager: RAGStatusManager

    celery_task_id: Optional[str] = None
    start_time: float = field(default_factory=time.monotonic)

    # ── helpers ──────────────────────────────────────────

    @property
    def source_id_str(self) -> str:
        return str(self.source_id)

    @property
    def tenant_id_str(self) -> str:
        return str(self.tenant_id)

    @property
    def elapsed_sec(self) -> float:
        return round(time.monotonic() - self.start_time, 2)

    # ── status shortcuts ─────────────────────────────────

    async def set_processing(self) -> None:
        """Mark current stage as PROCESSING."""
        await self.status_manager.transition_stage(
            doc_id=self.source_id,
            stage=self.stage_name,
            new_status=StageStatus.PROCESSING,
            celery_task_id=self.celery_task_id,
        )
        await self.session.flush()

    async def set_completed(self, metrics: Optional[Dict[str, Any]] = None) -> None:
        """Mark current stage as COMPLETED with optional metrics."""
        await self.status_manager.transition_stage(
            doc_id=self.source_id,
            stage=self.stage_name,
            new_status=StageStatus.COMPLETED,
            metrics=metrics,
        )

    async def set_failed(self, error: str) -> None:
        """Mark current stage as FAILED."""
        await self.status_manager.transition_stage(
            doc_id=self.source_id,
            stage=self.stage_name,
            new_status=StageStatus.FAILED,
            error=error[:500],
        )

    # ── idempotency ──────────────────────────────────────

    def _idem_key(self, model_alias: Optional[str] = None) -> str:
        return get_idempotency_key(
            self.tenant_id,
            self.source_id,
            self.stage_name.replace("embed.", "embed").replace("index.", "index"),
            model_alias,
        )

    async def check_idempotency(
        self,
        model_alias: Optional[str] = None,
        s3_key_field: str = "",
    ) -> Optional[Dict[str, Any]]:
        """
        Check Redis idempotency cache.

        Returns cached result dict if the stage was already processed
        and the S3 artifact still exists, else None.
        """
        idem_key = self._idem_key(model_alias)
        raw = await self.redis.get(idem_key)
        if not raw:
            return None

        try:
            cached = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None

        if s3_key_field:
            s3_key = cached.get(s3_key_field)
            if s3_key and not await s3_manager.object_exists(self.settings.S3_BUCKET_RAG, s3_key):
                return None

        return cached

    async def save_idempotency(
        self,
        data: Dict[str, Any],
        model_alias: Optional[str] = None,
        ttl: int = 86400,
    ) -> None:
        """Store result in Redis idempotency cache."""
        idem_key = self._idem_key(model_alias)
        await self.redis.setex(idem_key, ttl, json.dumps(data))

    # ── S3 shortcuts ─────────────────────────────────────

    async def s3_get(self, key: str) -> bytes:
        return await s3_manager.get_object(bucket=self.settings.S3_BUCKET_RAG, key=key)

    async def s3_put(self, key: str, content: bytes, content_type: str = "application/octet-stream") -> None:
        await s3_manager.upload_content_sync(
            bucket=self.settings.S3_BUCKET_RAG,
            key=key,
            content=content,
            content_type=content_type,
        )


# ── context manager ──────────────────────────────────────

@asynccontextmanager
async def _build_stage_context(
    stage_name: str,
    source_id: str,
    tenant_id: str,
    celery_task_id: Optional[str] = None,
) -> AsyncGenerator[IngestStageContext, None]:
    """
    Build IngestStageContext with all dependencies.
    Handles session, redis, and cleanup automatically.
    """
    settings = get_settings()
    redis_client: Optional[aioredis.Redis] = None

    try:
        redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

        async with get_worker_session() as session:
            t_uuid = uuid.UUID(tenant_id)
            s_uuid = uuid.UUID(source_id)

            repo_factory = AsyncRepositoryFactory(session, t_uuid)
            event_publisher = RAGEventPublisher(redis_client)
            status_manager = RAGStatusManager(session, repo_factory, event_publisher)

            ctx = IngestStageContext(
                source_id=s_uuid,
                tenant_id=t_uuid,
                stage_name=stage_name,
                session=session,
                redis=redis_client,
                settings=settings,
                repo_factory=repo_factory,
                event_publisher=event_publisher,
                status_manager=status_manager,
                celery_task_id=celery_task_id,
            )

            yield ctx

    finally:
        if redis_client:
            try:
                await redis_client.close()
                await redis_client.connection_pool.disconnect()
            except Exception:
                pass


# ── run_stage() — the main entry point ───────────────────

def run_stage(
    stage_name: str,
    source_id: str,
    tenant_id: str,
    celery_task: Any,
    execute_fn: Callable[["IngestStageContext"], Awaitable[T]],
    error_notify_fn: Optional[Callable] = None,
) -> Dict[str, Any]:
    """
    Universal runner for RAG ingest stages.

    Wraps a Celery task body with:
    - IngestStageContext construction & teardown
    - Error notification (falls back to notify_stage_error)
    - asyncio.run() bridge

    The *execute_fn* receives a ready-to-use IngestStageContext
    and must return a typed result dataclass that has `to_dict()`.

    Returns:
        Dict suitable for Celery chain passing.
    """
    celery_task_id = getattr(celery_task.request, "id", None)

    async def _run() -> Dict[str, Any]:
        async with _build_stage_context(
            stage_name=stage_name,
            source_id=source_id,
            tenant_id=tenant_id,
            celery_task_id=celery_task_id,
        ) as ctx:
            try:
                result = await execute_fn(ctx)
                return result.to_dict() if hasattr(result, "to_dict") else result
            except Exception as exc:
                logger.error(f"Error in {stage_name} for {source_id}: {exc}")
                try:
                    if error_notify_fn:
                        await error_notify_fn(source_id, tenant_id, stage_name, exc)
                    else:
                        await notify_stage_error(source_id, tenant_id, stage_name, exc)
                except Exception:
                    pass
                raise

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.error(f"Error in run_stage({stage_name}) for {source_id}: {exc}")
        raise
