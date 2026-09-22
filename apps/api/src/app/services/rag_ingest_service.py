"""
RAG service for managing ingest pipeline.

Owns document-level validation, progress calculation, cancel logic and durable
ingest-run creation.  Broker dispatch is intentionally performed only after
the transaction containing the upload/status/run has committed.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.repositories.factory import AsyncRepositoryFactory
from app.schemas.common import DocumentStatus, Step
from app.schemas.rag import IngestRequest, IngestResponse, IngestProgress
from app.services.document_artifacts import get_document_artifact_key
from app.services.rag_ingest_run_service import RAGIngestRunService
from app.services.rag_status_manager import RAGStatusManager, StageStatus

logger = get_logger(__name__)


class RAGIngestService:
    """Service for managing RAG ingest pipeline."""

    def __init__(
        self,
        session: AsyncSession,
        repo_factory: AsyncRepositoryFactory,
        status_manager: RAGStatusManager,
    ):
        self.session = session
        self.repo_factory = repo_factory
        self.status_manager = status_manager
        self.rag_repo = repo_factory.get_rag_documents_repository()
        self.source_repo = repo_factory.get_source_repository()
        self._runs = RAGIngestRunService(session, repo_factory, status_manager)

    async def _commit_and_dispatch(self, run_id: UUID) -> str:
        """Commit the command before publishing it; recovery can replay it."""
        await self.session.commit()
        from app.models.rag_ingest import RAGIngestOutbox
        from sqlalchemy import select
        outbox = (await self.session.execute(
            select(RAGIngestOutbox).where(RAGIngestOutbox.run_id == run_id)
        )).scalar_one()
        try:
            from app.workers.tasks_rag_ingest.dispatch import dispatch_rag_ingest_outbox
            dispatch_rag_ingest_outbox.delay(str(outbox.id))
        except Exception as exc:
            # Do not undo the durable command. The periodic reconciler will
            # deliver it once the broker is healthy again.
            logger.exception("RAG ingest command committed but initial dispatch failed: %s", exc)
        return str(outbox.id)

    # ── start ────────────────────────────────────────────

    async def start_ingest(self, request: IngestRequest) -> IngestResponse:
        """Start full ingest pipeline for a document."""
        logger.info(f"Starting ingest for document {request.document_id}")

        document = await self.rag_repo.get_by_id(self.repo_factory.tenant_id, request.document_id)
        if not document:
            raise ValueError(f"Document {request.document_id} not found")

        # The graph is the source of truth for active work.  The document
        # lifecycle field is a denormalised projection and must not be used to
        # decide whether another ingest may start.
        ingest_policy = await self.status_manager.get_ingest_policy(request.document_id)
        if not ingest_policy["start_allowed"]:
            if ingest_policy.get("start_reason") != "ingest_already_running":
                raise ValueError(f"Ingest is not allowed: {ingest_policy.get('start_reason')}")
            logger.warning(f"Document {request.document_id} is already being processed")
            return IngestResponse(
                document_id=request.document_id,
                status=DocumentStatus.PROCESSING,
                progress=await self._get_progress(request.document_id),
            )

        target_models = await self.status_manager._get_target_models(request.document_id)
        if not target_models:
            raise ValueError("No embedding models configured for this document tenant")
        await self.status_manager.start_ingest(request.document_id)
        run = await self._runs.create(
            request.document_id,
            trigger="upload",
            target_models=target_models,
        )
        await self._commit_and_dispatch(run.id)

        return IngestResponse(
            document_id=request.document_id,
            status=DocumentStatus.PROCESSING,
            progress=await self._get_progress(request.document_id),
        )

    # ── retry ────────────────────────────────────────────

    async def retry_failed(self, document_id: UUID, step: Step, model_alias: Optional[str] = None) -> Dict[str, Any]:
        """Retry a failed step."""
        logger.info(f"Retrying {step} for document {document_id}")

        document = await self.rag_repo.get_by_id(self.repo_factory.tenant_id, document_id)
        if not document:
            raise ValueError(f"Document {document_id} not found")

        if step == Step.EXTRACT:
            target_models = await self.status_manager._get_target_models(document_id)
            if not target_models:
                raise ValueError("No embedding models configured for this document tenant")
            await self.status_manager.retry_stage(document_id, "extract")
            run = await self._runs.create(document_id, trigger="retry", target_models=target_models)
        elif step == Step.EMBED:
            if not model_alias:
                raise ValueError("Model alias required for embed step")
            source = await self.source_repo.get_by_id(document_id)
            chunks_key = get_document_artifact_key(source.meta if source else None, "chunks")
            if not chunks_key:
                logger.warning(f"No chunks_key for {document_id}, falling back to full retry")
                target_models = await self.status_manager._get_target_models(document_id)
                await self.status_manager.retry_stage(document_id, "extract")
                run = await self._runs.create(document_id, trigger="retry", target_models=target_models)
            else:
                await self.status_manager.retry_stage(document_id, f"embed.{model_alias}")
                run = await self._runs.create(
                    document_id,
                    trigger="retry",
                    target_models=[model_alias],
                    resume_stage="embed",
                    payload={"model_alias": model_alias, "chunks_key": chunks_key},
                )
        else:
            raise ValueError(f"Unsupported step for retry: {step}. Use extract or embed.<model>.")

        task_id = await self._commit_and_dispatch(run.id)

        return {
            "document_id": str(document_id),
            "step": step.value,
            "model_alias": model_alias,
            "task_id": task_id,
            "status": "retry_started",
        }

    # ── reindex ──────────────────────────────────────────

    async def reindex_document(self, document_id: UUID, model_alias: str) -> Dict[str, Any]:
        """Reindex document with a (possibly new) embedding model."""
        logger.info(f"Reindexing document {document_id} with model {model_alias}")

        document = await self.rag_repo.get_by_id(self.repo_factory.tenant_id, document_id)
        if not document:
            raise ValueError(f"Document {document_id} not found")

        source = await self.source_repo.get_by_id(document_id)
        if not source:
            raise ValueError(f"Source for document {document_id} not found")

        chunks_key = get_document_artifact_key(source.meta, "chunks")
        if not chunks_key:
            logger.warning(f"No chunks_key found for {document_id}, falling back to full ingest")
            return await self.retry_failed(document_id, Step.EXTRACT)

        await self.status_manager.transition_stage(
            doc_id=document_id,
            stage=f"embed.{model_alias}",
            new_status=StageStatus.QUEUED,
        )
        await self.status_manager._reset_stage_if_needed(
            document_id,
            f"index.{model_alias}",
            StageStatus.PENDING,
            force=True,
        )
        await self.status_manager._update_aggregate_status(document_id)
        run = await self._runs.create(
            document_id,
            trigger="reindex",
            target_models=[model_alias],
            resume_stage="embed",
            payload={"model_alias": model_alias, "chunks_key": chunks_key},
        )
        task_id = await self._commit_and_dispatch(run.id)

        return {
            "document_id": str(document_id),
            "model_alias": model_alias,
            "task_id": task_id,
            "status": "reindex_started",
        }

    # ── progress ─────────────────────────────────────────

    async def get_progress(self, document_id: UUID) -> IngestProgress:
        """Get ingest progress for document (reads real status nodes)."""
        return await self._get_progress(document_id)

    async def _get_progress(self, document_id: UUID) -> IngestProgress:
        """Build IngestProgress from real status nodes via RAGStatusManager."""
        doc_status = await self.status_manager.get_document_status(document_id)
        pipeline = doc_status.get("pipeline", {})
        embeddings = doc_status.get("embeddings", {})
        index_nodes = doc_status.get("index", {})

        completed_steps: List[Step] = []
        failed_steps: List[Step] = []
        current_step = Step.EXTRACT
        models_processed: List[str] = []
        total_stages = 0
        completed_stages = 0

        # Pipeline stages mapping
        stage_step_map = {
            "extract": Step.EXTRACT,
            "normalize": Step.EXTRACT,
            "chunk": Step.CHUNK,
        }

        for stage_key, step in stage_step_map.items():
            info = pipeline.get(stage_key)
            if not info:
                continue
            total_stages += 1
            status = info.get("status", "")
            if status == StageStatus.COMPLETED.value:
                completed_stages += 1
                if step not in completed_steps:
                    completed_steps.append(step)
            elif status == StageStatus.FAILED.value:
                if step not in failed_steps:
                    failed_steps.append(step)
                current_step = step
            elif status in (StageStatus.PROCESSING.value, StageStatus.QUEUED.value):
                current_step = step

        # Embedding stages
        all_embed_done = bool(embeddings)
        for model_key, info in embeddings.items():
            total_stages += 1
            status = info.get("status", "")
            if status == StageStatus.COMPLETED.value:
                completed_stages += 1
                models_processed.append(model_key)
            elif status == StageStatus.FAILED.value:
                all_embed_done = False
                if Step.EMBED not in failed_steps:
                    failed_steps.append(Step.EMBED)
                current_step = Step.EMBED
            else:
                all_embed_done = False
                if status in (StageStatus.PROCESSING.value, StageStatus.QUEUED.value):
                    current_step = Step.EMBED

        if all_embed_done and embeddings:
            if Step.EMBED not in completed_steps:
                completed_steps.append(Step.EMBED)
            current_step = Step.INDEX

        # Index stages
        all_index_done = bool(index_nodes)
        for _, info in index_nodes.items():
            total_stages += 1
            status = info.get("status", "")
            if status == StageStatus.COMPLETED.value:
                completed_stages += 1
            elif status == StageStatus.FAILED.value:
                all_index_done = False
                if Step.INDEX not in failed_steps:
                    failed_steps.append(Step.INDEX)
                current_step = Step.INDEX
            else:
                all_index_done = False
                if status in (StageStatus.PROCESSING.value, StageStatus.QUEUED.value):
                    current_step = Step.INDEX

        if all_index_done and index_nodes:
            if Step.INDEX not in completed_steps:
                completed_steps.append(Step.INDEX)

        # Calculate progress percentage
        progress = round((completed_stages / total_stages * 100), 1) if total_stages > 0 else 0.0

        return IngestProgress(
            document_id=document_id,
            current_step=current_step,
            progress=progress,
            completed_steps=completed_steps,
            failed_steps=failed_steps,
            models_processed=models_processed,
            total_chunks=0,
            processed_chunks=0,
        )

    # ── cancel ───────────────────────────────────────────

    async def cancel_ingest(self, document_id: UUID) -> Dict[str, Any]:
        """Cancel ingest pipeline."""
        logger.info(f"Canceling ingest for document {document_id}")

        await self.status_manager.stop_ingest(document_id)
        await self.session.commit()

        return {
            "document_id": str(document_id),
            "status": "cancelled",
            "canceled_at": datetime.now(timezone.utc).isoformat(),
        }
