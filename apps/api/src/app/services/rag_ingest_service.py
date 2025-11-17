"""
RAG service for managing ingest pipeline
"""
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from uuid import UUID

from app.schemas.rag import IngestRequest, IngestResponse, IngestProgress
from app.schemas.common import DocumentStatus, Step, ChunkProfile
from app.repositories.factory import AsyncRepositoryFactory
from app.workers.tasks_rag_ingest import (
    extract_document,
    normalize_document,
    chunk_document,
    embed_chunks_model,
    index_model,
)
from celery import chain, group
from app.core.logging import get_logger

logger = get_logger(__name__)


class RAGIngestService:
    """Service for managing RAG ingest pipeline"""
    
    def __init__(self, repo_factory: AsyncRepositoryFactory):
        self.repo_factory = repo_factory
        self.rag_repo = repo_factory.get_rag_documents_repository()
        self.source_repo = repo_factory.get_source_repository()
    
    async def start_ingest(self, request: IngestRequest) -> IngestResponse:
        """
        Start ingest pipeline for document
        
        Args:
            request: Ingest request
            
        Returns:
            IngestResponse: Response with status and progress
        """
        logger.info(f"Starting ingest for document {request.document_id}")
        
        # Get document
        document = await self.rag_repo.get_by_id(self.repo_factory.tenant_id, request.document_id)
        if not document:
            raise ValueError(f"Document {request.document_id} not found")
        
        # Check if already processing
        if document.status in [DocumentStatus.EXTRACTING, DocumentStatus.CHUNKING, 
                                    DocumentStatus.EMBEDDING, DocumentStatus.INDEXING]:
            logger.warning(f"Document {request.document_id} is already being processed")
            return IngestResponse(
                document_id=request.document_id,
                status=DocumentStatus(document.status),
                progress=await self._get_progress(request.document_id),
                ingest_run_id=UUID("00000000-0000-0000-0000-000000000000")
            )
        
        # Update status nodes through RAGStatusManager
        from app.services.rag_status_manager import RAGStatusManager
        from app.core.db import get_session_factory
        
        # Get session for RAGStatusManager
        session_factory = get_session_factory()
        async with session_factory() as session:
            status_manager = RAGStatusManager(session, self.repo_factory)
            
            # Start ingest: переводит все pending этапы в queued
            await status_manager.start_ingest(request.document_id)
            
            # Update document status to queued
            await self.rag_repo.update(self.repo_factory.tenant_id, request.document_id, status=DocumentStatus.QUEUED)
        
        # Start ingest pipeline with parallel embedding
        # Get embedding models from tenant (not from config)
        from celery import group, chord
        from app.services.rag_status_manager import RAGStatusManager
        from app.core.db import get_session_factory
        
        # Get tenant's embedding models
        session_factory = get_session_factory()
        async with session_factory() as session:
            status_manager = RAGStatusManager(session, self.repo_factory)
            embedding_models = await status_manager._get_target_models(request.document_id)
        
        if not embedding_models:
            logger.warning(f"No embedding models configured for tenant {self.repo_factory.tenant_id}, using default")
            from app.core.config import get_embedding_models
            embedding_models = get_embedding_models()
        
        # Create pipeline: extract -> normalize -> chunk -> [parallel embeddings]
        # extract_document(signature): (source_id, tenant_id)
        extract_task = extract_document.s(
            str(request.document_id),
            str(self.repo_factory.tenant_id)
        )

        # normalize_document(signature): (extract_result, tenant_id)
        normalize_task = normalize_document.s(str(self.repo_factory.tenant_id))

        # chunk_document(signature): (normalize_result, tenant_id)
        chunk_task = chunk_document.s(str(self.repo_factory.tenant_id))

        # parallel (embed -> index) per model
        embedding_index_chains = [
            chain(
                embed_chunks_model.s(str(self.repo_factory.tenant_id), model_alias),
                index_model.s(str(self.repo_factory.tenant_id)),
            )
            for model_alias in embedding_models
        ]

        pipeline = chain(extract_task, normalize_task, chunk_task, group(embedding_index_chains))
        
        # Start the pipeline
        pipeline.apply_async()
        
        # Manually trigger commit after embeddings complete
        # Note: This is a workaround since chord doesn't work well with chain
        # In production, each embedding task should check if all are done and trigger commit
        
        # Create ingest run record
        ingest_run_id = UUID("00000000-0000-0000-0000-000000000000")  # Mock ID
        
        logger.info(f"Started ingest pipeline for document {request.document_id}")
        
        return IngestResponse(
            document_id=request.document_id,
            status=DocumentStatus.QUEUED,
            progress=await self._get_progress(request.document_id),
            ingest_run_id=ingest_run_id
        )
    
    async def retry_failed(self, document_id: UUID, step: Step, model_alias: str = None) -> Dict[str, Any]:
        """
        Retry failed step
        
        Args:
            document_id: Document ID
            step: Step to retry
            model_alias: Model alias (for embed step)
            
        Returns:
            Dict: Retry result
        """
        logger.info(f"Retrying {step} for document {document_id}")
        
        # Get document
        document = await self.rag_repo.get_by_id(self.repo_factory.tenant_id, document_id)
        if not document:
            raise ValueError(f"Document {document_id} not found")
        
        # Start appropriate task based on step
        if step == Step.EXTRACT:
            # Full pipeline: extract → normalize → chunk → group(embed)
            # Get tenant models (same logic as start_ingest)
            from app.services.rag_status_manager import RAGStatusManager
            from app.core.db import get_session_factory
            session_factory = get_session_factory()
            async with session_factory() as session:
                status_manager = RAGStatusManager(session, self.repo_factory)
                embedding_models = await status_manager._get_target_models(document_id)
            if not embedding_models:
                from app.core.config import get_embedding_models
                embedding_models = get_embedding_models()

            extract_task = extract_document.s(str(document_id), str(self.repo_factory.tenant_id))
            normalize_task = normalize_document.s(str(self.repo_factory.tenant_id))
            chunk_task = chunk_document.s(str(self.repo_factory.tenant_id))
            embedding_index_chains = [
                chain(
                    embed_chunks_model.s(str(self.repo_factory.tenant_id), m),
                    index_model.s(str(self.repo_factory.tenant_id)),
                )
                for m in embedding_models
            ]
            task = chain(extract_task, normalize_task, chunk_task, group(embedding_index_chains)).apply_async()
        elif step == Step.EMBED:
            if not model_alias:
                raise ValueError("Model alias required for embed step")
            # Allow direct restart of embed: task will fetch chunks by source_id
            task = embed_chunks_model.delay({"source_id": str(document_id)}, str(self.repo_factory.tenant_id), model_alias)
        else:
            raise ValueError(f"Unsupported step for retry: {step}. Use extract or embed.<model>.")
        
        return {
            "document_id": document_id,
            "step": step,
            "model_alias": model_alias,
            "task_id": task.id,
            "status": "retry_started"
        }
    
    async def get_progress(self, document_id: UUID) -> IngestProgress:
        """
        Get ingest progress for document
        
        Args:
            document_id: Document ID
            
        Returns:
            IngestProgress: Current progress
        """
        return await self._get_progress(document_id)
    
    async def _get_progress(self, document_id: UUID) -> IngestProgress:
        """Internal method to get progress"""
        # Get document
        document = await self.rag_repo.get_by_id(self.repo_factory.tenant_id, document_id)
        if not document:
            raise ValueError(f"Document {document_id} not found")
        
        # Mock progress calculation
        status = DocumentStatus(document.status)
        
        completed_steps = []
        failed_steps = []
        current_step = Step.EXTRACT
        progress = 0.0
        
        if status == DocumentStatus.READY:
            completed_steps = [Step.EXTRACT, Step.CHUNK, Step.EMBED, Step.INDEX]
            current_step = Step.INDEX
            progress = 100.0
        elif status == DocumentStatus.EXTRACTING:
            current_step = Step.EXTRACT
            progress = 25.0
        elif status == DocumentStatus.CHUNKING:
            completed_steps = [Step.EXTRACT]
            current_step = Step.CHUNK
            progress = 50.0
        elif status == DocumentStatus.EMBEDDING:
            completed_steps = [Step.EXTRACT, Step.CHUNK]
            current_step = Step.EMBED
            progress = 75.0
        elif status == DocumentStatus.INDEXING:
            completed_steps = [Step.EXTRACT, Step.CHUNK, Step.EMBED]
            current_step = Step.INDEX
            progress = 90.0
        elif status == DocumentStatus.FAILED:
            failed_steps = [Step.EXTRACT]  # Mock failed step
            progress = 0.0
        
        return IngestProgress(
            document_id=document_id,
            current_step=current_step,
            progress=progress,
            completed_steps=completed_steps,
            failed_steps=failed_steps,
            models_processed=["all-MiniLM-L6-v2"],  # Mock
            total_chunks=0,  # Mock
            processed_chunks=0  # Mock
        )
    
    async def cancel_ingest(self, document_id: UUID) -> Dict[str, Any]:
        """
        Cancel ingest pipeline
        
        Args:
            document_id: Document ID
            
        Returns:
            Dict: Cancel result
        """
        logger.info(f"Canceling ingest for document {document_id}")
        
        # Update document status to canceled
        await self.rag_repo.update_status(document_id, DocumentStatus.CANCELED)
        
        return {
            "document_id": document_id,
            "status": "canceled",
            "canceled_at": datetime.now(timezone.utc).isoformat()
        }
    
    async def get_ingest_runs(self, document_id: UUID = None, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get ingest runs
        
        Args:
            document_id: Filter by document ID
            limit: Limit results
            
        Returns:
            List of ingest runs
        """
        # Mock implementation
        return []
    
    async def cleanup_old_runs(self, days: int = 30) -> int:
        """
        Cleanup old completed ingest runs
        
        Args:
            days: Days to keep
            
        Returns:
            Number of cleaned runs
        """
        logger.info(f"Cleaning up ingest runs older than {days} days")
        
        # Mock implementation
        return 0