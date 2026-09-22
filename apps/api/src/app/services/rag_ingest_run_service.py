"""Durable command creation for document RAG ingest.

The request transaction writes both the run and its dispatch command.  Nothing
is sent to the broker until that transaction is committed by ``dispatch``.
This is intentionally forward-only: every stage leaves an artifact/result and
retries create a new fenced generation instead of rolling work back.
"""
from __future__ import annotations

from typing import Any, Iterable
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.rag_ingest import RAGIngestOutbox, RAGIngestRun, RAGIngestStageRun
from app.repositories.factory import AsyncRepositoryFactory
from app.services.rag_status_manager import RAGStatusManager


class RAGIngestRunService:
    def __init__(
        self,
        session: AsyncSession,
        repo_factory: AsyncRepositoryFactory,
        status_manager: RAGStatusManager,
    ) -> None:
        self.session = session
        self.repo_factory = repo_factory
        self.status_manager = status_manager

    async def create(
        self,
        document_id: UUID,
        *,
        trigger: str,
        target_models: Iterable[str],
        resume_stage: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> RAGIngestRun:
        document = await self.repo_factory.get_rag_documents_repository().get_by_id(
            self.repo_factory.tenant_id, document_id
        )
        if not document:
            raise ValueError(f"Document {document_id} not found")

        # The row is in the request transaction, so concurrent starts serialize
        # through the document update and every worker can fence by generation.
        document.ingest_generation = int(document.ingest_generation or 0) + 1
        generation = document.ingest_generation
        models = list(dict.fromkeys(str(item) for item in target_models if item))
        run = RAGIngestRun(
            doc_id=document_id,
            tenant_id=self.repo_factory.tenant_id,
            generation=generation,
            trigger=trigger,
            status="queued",
            target_models=models,
            resume_stage=resume_stage,
        )
        self.session.add(run)
        await self.session.flush()
        stage_keys = self._stage_keys(resume_stage, models)
        self.session.add_all(
            RAGIngestStageRun(run_id=run.id, stage_key=stage_key, status="pending")
            for stage_key in stage_keys
        )
        self.session.add(RAGIngestOutbox(
            run_id=run.id,
            command="dispatch_pipeline",
            payload=payload or {},
            status="pending",
        ))
        await self.session.flush()
        return run

    @staticmethod
    def _stage_keys(resume_stage: str | None, models: list[str]) -> list[str]:
        if resume_stage == "embed":
            return [item for model in models for item in (f"embed.{model}", f"index.{model}")]
        return ["extract", "normalize", "chunk"] + [
            item for model in models for item in (f"embed.{model}", f"index.{model}")
        ]
