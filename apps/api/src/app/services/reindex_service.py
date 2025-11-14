"""
Reindex Service for document processing and vector indexing
"""
import asyncio
import enum
from typing import Optional, Dict, Any, List, AsyncGenerator
from uuid import UUID
from datetime import datetime, timezone
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.models.rag import RAGDocument, RAGChunk, DocumentScope, DocumentStatus
from app.models.user import Users
from app.core.rbac import RBACValidator

logger = logging.getLogger(__name__)


class ReindexJobStatus(str, enum.Enum):
    """Reindex job status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReindexTriggerType(str, enum.Enum):
    """Types of reindex triggers"""
    FULL = "full"
    INCREMENTAL = "incremental"
    DOCUMENT = "document"
    TENANT = "tenant"
    SCOPE = "scope"


class ReindexJob:
    """Reindex job tracking"""
    
    def __init__(self, job_id: str, job_type: ReindexTriggerType, actor: Users):
        self.job_id = job_id
        self.job_type = job_type
        self.actor = actor
        self.status = ReindexJobStatus.PENDING
        self.progress_percentage = 0.0
        
        # Target filtering
        self.tenant_id: Optional[UUID] = None
        self.document_id: Optional[UUID] = None
        self.scope: Optional[DocumentScope] = None
        
        # Processing stats
        self.documents_processed = 0
        self.chunks_processed = 0
        self.current_document: Optional[str] = None
        
        # Timestamps
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.estimated_completion: Optional[datetime] = None
        
        # Error tracking
        self.error_message: Optional[str] = None
        self.error_details: Optional[Dict[str, Any]] = None


class ReindexService:
    """Service for managing document reindexing operations"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.jobs: Dict[str, ReindexJob] = {}
    
    async def start_reindex(
        self,
        actor: Users,
        trigger_type: ReindexTriggerType,
        tenant_id: Optional[UUID] = JFNone,
        document_id: Optional[UUID] = None,
        scope: Optional[DocumentScope] = None,
        force: bool = False,
        incremental: bool = True,
    ) -> ReindexJob:
        """
        Start a reindex operation
        
        Args:
            actor: User initiating the reindex
            trigger_type: Type of reindex trigger
            tenant_id: Target tenant (optional)
            document_id: Target document (optional)
            scope: Target scope (optional)
            force: Force reindex even if already processed
            incremental: Perform incremental reindex
        """
        
        # Permission check
        permission_check = RBACValidator.can_trigger_reindex(actor)
        if not permission_check.allowed:
            raise ValueError(f"Permission denied: {permission_check.reason}")
        
        # Generate job ID
        job_id = f"reindex_{int(datetime.now().timestamp())}"
        
        # Create job
        job = ReindexJob(job_id, trigger_type, actor)
        job.tenant_id = tenant_id
        job.document_id = document_id
        job.scope = scope
        job.started_at = datetime.now(timezone.utc)
        
        # Validate that another reindex isn't already running
        if await self._is_reindex_running():
            raise ValueError("Reindex operation is already running")
        
        # Store job
        self.jobs[job_id] = job
        
        # Start background processing
        asyncio.create_task(self._process_reindex(job))
        
        logger.info(f"Started reindex job {job_id} triggered by {actor.id}")
        
        return job
    
    async def _process_reindex(self, job: ReindexJob):
        """
        Process reindex operation
        """
        try:
            job.status = ReindexJobStatus.RUNNING
            
            # Get documents to process
            documents_query = await self._build_documents_query(
                job.tenant_id, job.document_id, job.scope
            )
            
            result = await self.session.execute(Documents_query)
            documents = result.scalars().all()
            
            total_docs = len(documents)
            job.documents_processed = 0
            
            for doc in documents:
                job.current_document = doc.filename
                await self._reindex_document(doc)
                job.documents_processed += 1
                
                # Update progress
                job.progress_percentage = (job.documents_processed / total_docs) * 100
                
                # Log progress
                logger.info(f"Reindex progress: {job.progress_percentage:.1f}% - {doc.filename}")
            
            # Mark as completed
            job.status = ReindexJobStatus.COMPLETED
            job.completed_at = datetime.now(timezone.utc)
            job.progress_percentage = 100.0
            
            logger.info(f"Completed reindex job {job.job_id}")
            
        except Exception as e:
            job.status = ReindexJobStatus.FAILED
            job.completed_at = datetime.now(timezone.utc)
            job.error_message = str(e)
            job.error_details = {"exception_type": type(e).__name__}
            
            logger.error(f"Reindex job {job.job_id} failed: {e}")
    
    async def _build_documents_query(self, tenant_id: Optional[UUID], document_id: Optional[UUID], scope: Optional[DocumentScope]):
        """
        Build query to select documents for reindexing
        """
        query = select(RAGDocument).options(selectinload(RAGDocument.chunks))
        
        # Filter by document ID (highest priority)
        if document_id:
            query = query.where(RAGDocument.id == document_id)
            return query
        
        # Filter by scope
        if scope:
            query = query.where(RAGDocument.scope == scope)
        
        # Filter by tenant
        if tenant_id:
            query = query.where(RAGDocument.tenant_id == tenant_id)
        
        # Only process documents that are in processed status
        query = query.where(RAGDocument.status == DocumentStatus.PROCESSED)
        
        return query
    
    async def _reindex_document(self, document: RAGDocument):
        """
        Reindex a single document
        """
        chunks = document.chunks
        
        for chunk in chunks:
            try:
                # Update chunk metadata
                chunk.scope = chunk.scope or document.scope
                chunk.tenant_id = chunk.tenant_id or document.tenant_id
                
                # Here you would update Qdrant vector database
                # await self._update_qdrant_chunk(chunk)
                
                await self.session.commit()
                
            except Exception as e:
                logger.error(f"Failed to reindex chunk {chunk.id}: {e}")
                raise
    
    async def get_job_status(self, job_id: str) -> Optional[ReindexJob]:
        """
        Get status of reindex job
        """
        return self.jobs.get(job_id)
    
    async def _is_reindex_running(self) -> bool:
        """
        Check if any reindex operations are currently running
        """
        for job in self.jobs.values():
            if job.status == ReindexJobStatus.RUNNING:
                return True
        return False