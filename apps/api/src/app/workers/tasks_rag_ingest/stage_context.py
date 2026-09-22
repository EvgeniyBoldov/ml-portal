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
import hashlib
import json
import time
import traceback
import uuid
from datetime import datetime, timezone
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
from sqlalchemy import select

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
    run_id: Optional[uuid.UUID] = None
    generation: Optional[int] = None
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
        await self._update_stage_run(status="processing", celery_task_id=self.celery_task_id)

    async def set_completed(self, metrics: Optional[Dict[str, Any]] = None) -> None:
        """Mark current stage as COMPLETED with optional metrics."""
        await self.status_manager.transition_stage(
            doc_id=self.source_id,
            stage=self.stage_name,
            new_status=StageStatus.COMPLETED,
            metrics=metrics,
            model_version=(metrics or {}).get("model_version"),
        )
        await self._update_stage_run(status="completed", metrics=metrics)

    async def set_failed(self, error: str) -> None:
        """Mark current stage as FAILED."""
        await self.status_manager.transition_stage(
            doc_id=self.source_id,
            stage=self.stage_name,
            new_status=StageStatus.FAILED,
            error=error[:500],
        )
        await self._update_stage_run(status="failed", error=error[:500])
        if self.run_id is not None:
            from app.models.rag_ingest import RAGIngestRun, RAGIngestStageOutbox
            command = (await self.session.execute(
                select(RAGIngestStageOutbox).where(
                    RAGIngestStageOutbox.run_id == self.run_id,
                    RAGIngestStageOutbox.stage_key == self.stage_name,
                )
            )).scalar_one_or_none()
            if command:
                command.status = "failed"
                command.last_error = error[:500]
            run = (await self.session.execute(
                select(RAGIngestRun).where(RAGIngestRun.id == self.run_id)
            )).scalar_one_or_none()
            if run and run.status in {"queued", "running"}:
                run.status = "failed"
                run.error_short = error[:500]
                run.finished_at = datetime.now(timezone.utc)
                await self.session.flush()

    async def is_current_generation(self) -> bool:
        if self.run_id is None or self.generation is None:
            return True
        from app.models.rag import RAGDocument
        from app.models.rag_ingest import RAGIngestRun
        result = await self.session.execute(
            select(RAGDocument.ingest_generation, RAGIngestRun.status).where(
                RAGDocument.id == self.source_id,
                RAGIngestRun.id == self.run_id,
                RAGIngestRun.doc_id == self.source_id,
            )
        )
        row = result.first()
        return bool(row and int(row[0] or 0) == self.generation and row[1] in {"queued", "running"})

    async def mark_stale(self) -> None:
        """Finish an obsolete run without touching the current UI projection."""
        if self.run_id is None:
            return
        from app.models.rag_ingest import RAGIngestRun, RAGIngestStageOutbox
        await self._update_stage_run(status="cancelled", error="superseded by a newer ingest generation")
        command = (await self.session.execute(
            select(RAGIngestStageOutbox).where(
                RAGIngestStageOutbox.run_id == self.run_id,
                RAGIngestStageOutbox.stage_key == self.stage_name,
            )
        )).scalar_one_or_none()
        if command:
            command.status = "cancelled"
        run = (await self.session.execute(
            select(RAGIngestRun).where(RAGIngestRun.id == self.run_id)
        )).scalar_one_or_none()
        if run and run.status in {"queued", "running"}:
            run.status = "cancelled"
            run.finished_at = datetime.now(timezone.utc)
        await self.session.flush()

    async def record_result(self, result: Dict[str, Any]) -> list[str]:
        """Store the typed inter-stage payload durably, alongside a checksum."""
        digest = hashlib.sha256(json.dumps(result, sort_keys=True, default=str).encode("utf-8")).hexdigest()
        await self._update_stage_run(result=result, output_fingerprint=digest)
        command_ids = await self._enqueue_next_stages(result)
        if self.run_id is not None:
            from app.models.rag_ingest import RAGIngestRun, RAGIngestStageRun, RAGIngestStageOutbox
            command = (await self.session.execute(
                select(RAGIngestStageOutbox).where(
                    RAGIngestStageOutbox.run_id == self.run_id,
                    RAGIngestStageOutbox.stage_key == self.stage_name,
                )
            )).scalar_one_or_none()
            if command:
                command.status = "completed"
            states = (await self.session.execute(
                select(RAGIngestStageRun.status).where(RAGIngestStageRun.run_id == self.run_id)
            )).scalars().all()
            if states and all(state == "completed" for state in states):
                run = (await self.session.execute(
                    select(RAGIngestRun).where(RAGIngestRun.id == self.run_id)
                )).scalar_one_or_none()
                if run and run.status in {"queued", "running"}:
                    run.status = "completed"
                    run.finished_at = datetime.now(timezone.utc)
                    from app.models.rag_ingest import RAGIngestStageOutbox
                    shadow = (await self.session.execute(
                        select(RAGIngestStageOutbox).where(
                            RAGIngestStageOutbox.run_id == self.run_id,
                            RAGIngestStageOutbox.stage_key == "shadow",
                        )
                    )).scalar_one_or_none()
                    if shadow is None:
                        shadow = RAGIngestStageOutbox(
                            run_id=self.run_id,
                            stage_key="shadow",
                            payload={"source_id": str(self.source_id)},
                            status="pending",
                        )
                        self.session.add(shadow)
                        await self.session.flush()
                    command_ids.append(str(shadow.id))
        return command_ids

    async def _enqueue_next_stages(self, result: Dict[str, Any]) -> list[str]:
        """Append forward-only commands; no Celery canvas carries state."""
        if self.run_id is None:
            return []
        from app.models.rag_ingest import RAGIngestRun, RAGIngestStageOutbox
        run = (await self.session.execute(
            select(RAGIngestRun).where(RAGIngestRun.id == self.run_id)
        )).scalar_one_or_none()
        if not run:
            return []
        if self.stage_name == "extract":
            next_keys = ["normalize"]
        elif self.stage_name == "normalize":
            next_keys = ["chunk"]
        elif self.stage_name == "chunk":
            next_keys = [f"embed.{model}" for model in (run.target_models or [])]
        elif self.stage_name.startswith("embed."):
            next_keys = [f"index.{self.stage_name.split('.', 1)[1]}"]
        else:
            next_keys = []
        command_ids: list[str] = []
        for stage_key in next_keys:
            command = (await self.session.execute(
                select(RAGIngestStageOutbox).where(
                    RAGIngestStageOutbox.run_id == self.run_id,
                    RAGIngestStageOutbox.stage_key == stage_key,
                )
            )).scalar_one_or_none()
            if command is None:
                command = RAGIngestStageOutbox(
                    run_id=self.run_id, stage_key=stage_key, payload=result, status="pending"
                )
                self.session.add(command)
                await self.session.flush()
            command_ids.append(str(command.id))
        return command_ids

    async def _update_stage_run(
        self,
        *,
        status: Optional[str] = None,
        celery_task_id: Optional[str] = None,
        result: Optional[Dict[str, Any]] = None,
        metrics: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        output_fingerprint: Optional[str] = None,
    ) -> None:
        if self.run_id is None:
            return
        from app.models.rag_ingest import RAGIngestStageRun
        stage_run = (await self.session.execute(
            select(RAGIngestStageRun).where(
                RAGIngestStageRun.run_id == self.run_id,
                RAGIngestStageRun.stage_key == self.stage_name,
            )
        )).scalar_one_or_none()
        if not stage_run:
            return
        now = datetime.now(timezone.utc)
        if status:
            stage_run.status = status
            if status == "processing":
                stage_run.started_at = stage_run.started_at or now
            elif status in {"completed", "failed", "cancelled"}:
                stage_run.finished_at = now
        if celery_task_id is not None:
            stage_run.celery_task_id = celery_task_id
        if result is not None:
            stage_run.result_json = result
        if metrics is not None:
            stage_run.metrics_json = metrics
        if error is not None:
            stage_run.error_short = error
        if output_fingerprint is not None:
            stage_run.output_fingerprint = output_fingerprint
        await self.session.flush()

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
    run_id: Optional[str] = None,
    generation: Optional[int] = None,
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
                run_id=uuid.UUID(run_id) if run_id else None,
                generation=generation,
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
    run_id: Optional[str] = None,
    generation: Optional[int] = None,
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
            run_id=run_id,
            generation=generation,
        ) as ctx:
            try:
                if not await ctx.is_current_generation():
                    logger.info("Skipping stale RAG stage: run=%s stage=%s source=%s", run_id, stage_name, source_id)
                    await ctx.mark_stale()
                    await ctx.session.commit()
                    return {"source_id": source_id, "stale": True}
                result = await execute_fn(ctx)
                data = result.to_dict() if hasattr(result, "to_dict") else result
                command_ids = await ctx.record_result(data)
                await ctx.session.commit()
                logger.info(
                    "RAG stage result persisted: run=%s stage=%s source=%s fingerprint=%s next_commands=%s",
                    run_id, stage_name, source_id,
                    hashlib.sha256(json.dumps(data, sort_keys=True, default=str).encode("utf-8")).hexdigest(),
                    command_ids,
                )
                for command_id in command_ids:
                    from app.workers.tasks_rag_ingest.dispatch import dispatch_rag_ingest_stage_outbox
                    dispatch_rag_ingest_stage_outbox.delay(command_id)
                return data
            except Exception as exc:
                logger.error(
                    "RAG ingest stage failed: stage=%s source_id=%s tenant_id=%s celery_task_id=%s error=%s",
                    stage_name,
                    source_id,
                    tenant_id,
                    celery_task_id,
                    exc,
                    exc_info=True,
                )
                stage_error = f"{type(exc).__name__}: {exc}"
                try:
                    await ctx.set_failed(stage_error)
                    await ctx.session.commit()
                except Exception as status_exc:
                    logger.error(
                        "Failed to persist FAILED status in-stage: stage=%s source_id=%s error=%s",
                        stage_name,
                        source_id,
                        status_exc,
                        exc_info=True,
                    )
                    try:
                        if error_notify_fn:
                            await error_notify_fn(source_id, tenant_id, stage_name, exc)
                        else:
                            await notify_stage_error(source_id, tenant_id, stage_name, exc)
                    except Exception as notify_exc:
                        logger.error(
                            "Fallback stage error notification failed: stage=%s source_id=%s error=%s",
                            stage_name,
                            source_id,
                            notify_exc,
                            exc_info=True,
                        )
                raise

    try:
        return asyncio.run(_run())
    except Exception as exc:
        logger.error(
            "run_stage bubbled exception: stage=%s source_id=%s tenant_id=%s error=%s\n%s",
            stage_name,
            source_id,
            tenant_id,
            exc,
            traceback.format_exc(),
        )
        raise
