"""
RAG Status Repository for managing document status nodes
"""
from __future__ import annotations
from typing import List, Optional, Dict, Any
from uuid import UUID
from datetime import datetime, timezone
from app.core.logging import get_logger

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from sqlalchemy.orm import selectinload

from app.models.rag_ingest import RAGStatus
from app.models.rag import RAGDocument
from app.repositories.base import AsyncRepository


logger = get_logger(__name__)


class AsyncRAGStatusRepository(AsyncRepository):
    """Async repository for RAGStatus model operations with tenant isolation"""
    
    def __init__(self, session: AsyncSession, tenant_id: Optional[UUID] = None, user_id: Optional[UUID] = None):
        super().__init__(session, RAGStatus)
        self.tenant_id = tenant_id
        self.user_id = user_id
    
    def _build_tenant_filter(self, stmt):
        """Add tenant isolation via join to ragdocuments"""
        if self.tenant_id:
            stmt = stmt.join(RAGDocument, RAGStatus.doc_id == RAGDocument.id)
            stmt = stmt.where(RAGDocument.tenant_id == self.tenant_id)
        return stmt
    
    async def get_nodes_by_doc_id(self, doc_id: UUID) -> List[RAGStatus]:
        """Get all status nodes for a document with tenant isolation"""
        stmt = select(RAGStatus).where(RAGStatus.doc_id == doc_id)
        stmt = self._build_tenant_filter(stmt)
        stmt = stmt.order_by(RAGStatus.node_type, RAGStatus.node_key)
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def get_node(self, doc_id: UUID, node_type: str, node_key: str) -> Optional[RAGStatus]:
        """Get specific status node with tenant isolation"""
        stmt = select(RAGStatus).where(
            RAGStatus.doc_id == doc_id,
            RAGStatus.node_type == node_type,
            RAGStatus.node_key == node_key
        )
        stmt = self._build_tenant_filter(stmt)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    async def upsert_node(
        self, 
        doc_id: UUID, 
        node_type: str, 
        node_key: str, 
        status: str,
        celery_task_id: Optional[str] = None,
        model_version: Optional[str] = None,
        modality: Optional[str] = None,
        error_short: Optional[str] = None,
        metrics_json: Optional[Dict[str, Any]] = None,
        started_at: Optional[datetime] = None,
        finished_at: Optional[datetime] = None
    ) -> RAGStatus:
        """Create or update status node"""
        existing = await self.get_node(doc_id, node_type, node_key)
        
        if existing:
            # Update existing node
            existing.status = status
            if celery_task_id is not None:
                existing.celery_task_id = celery_task_id
            # Preserve version/modality unless explicitly provided.
            if model_version is not None:
                existing.model_version = model_version
            if modality is not None:
                existing.modality = modality
            existing.error_short = error_short
            existing.metrics_json = metrics_json
            if started_at:
                existing.started_at = started_at
            if finished_at:
                existing.finished_at = finished_at
            existing.updated_at = datetime.now(timezone.utc)
            await self.session.flush()
            return existing
        else:
            # Create new node only if document exists to avoid FK violations
            result = await self.session.execute(
                select(RAGDocument.id).where(RAGDocument.id == doc_id)
            )
            doc_exists = result.scalar_one_or_none()

            if not doc_exists:
                logger.warning(
                    "Skipping rag_status upsert for non-existent document: %s (node_type=%s, node_key=%s)",
                    doc_id,
                    node_type,
                    node_key,
                )
                # Do not create status node if document row is missing
                return existing

            new_node = RAGStatus(
                doc_id=doc_id,
                node_type=node_type,
                node_key=node_key,
                status=status,
                celery_task_id=celery_task_id,
                model_version=model_version,
                modality=modality,
                error_short=error_short,
                metrics_json=metrics_json,
                started_at=started_at,
                finished_at=finished_at
            )
            self.session.add(new_node)
            await self.session.flush()
            return new_node
    
    async def delete_nodes_by_doc_id(self, doc_id: UUID) -> int:
        """Delete all status nodes for a document with tenant isolation"""
        # Build delete with tenant filter via subquery
        if self.tenant_id:
            # Delete only if doc belongs to tenant
            subq = select(RAGDocument.id).where(
                RAGDocument.id == doc_id,
                RAGDocument.tenant_id == self.tenant_id
            )
            result = await self.session.execute(
                delete(RAGStatus).where(
                    RAGStatus.doc_id == doc_id,
                    RAGStatus.doc_id.in_(subq)
                )
            )
        else:
            result = await self.session.execute(
                delete(RAGStatus).where(RAGStatus.doc_id == doc_id)
            )
        return result.rowcount
    
    async def get_pipeline_nodes(self, doc_id: UUID) -> List[RAGStatus]:
        """Get pipeline nodes (upload, extract, chunk, index) with tenant isolation"""
        stmt = select(RAGStatus).where(
            RAGStatus.doc_id == doc_id,
            RAGStatus.node_type == 'pipeline'
        )
        stmt = self._build_tenant_filter(stmt)
        stmt = stmt.order_by(RAGStatus.node_key)
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def get_embedding_nodes(self, doc_id: UUID) -> List[RAGStatus]:
        """Get embedding nodes (by model) with tenant isolation"""
        stmt = select(RAGStatus).where(
            RAGStatus.doc_id == doc_id,
            RAGStatus.node_type == 'embedding'
        )
        stmt = self._build_tenant_filter(stmt)
        stmt = stmt.order_by(RAGStatus.node_key)
        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def get_index_nodes(self, doc_id: UUID) -> List[RAGStatus]:
        """Get index nodes (by model) with tenant isolation"""
        stmt = select(RAGStatus).where(
            RAGStatus.doc_id == doc_id,
            RAGStatus.node_type == 'index'
        )
        stmt = self._build_tenant_filter(stmt)
        stmt = stmt.order_by(RAGStatus.node_key)
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def get_nodes_by_status(self, status: str) -> List[RAGStatus]:
        """Get all nodes with specific status and tenant isolation"""
        stmt = select(RAGStatus).where(RAGStatus.status == status)
        stmt = self._build_tenant_filter(stmt)
        result = await self.session.execute(stmt)
        return result.scalars().all()
    
    async def update_node_status(
        self, 
        doc_id: UUID, 
        node_type: str, 
        node_key: str, 
        status: str,
        error_short: Optional[str] = None,
        metrics_json: Optional[Dict[str, Any]] = None
    ) -> bool:
        """Update node status and related fields"""
        result = await self.session.execute(
            update(RAGStatus).where(
                RAGStatus.doc_id == doc_id,
                RAGStatus.node_type == node_type,
                RAGStatus.node_key == node_key
            ).values(
                status=status,
                error_short=error_short,
                metrics_json=metrics_json,
                updated_at=datetime.now(timezone.utc)
            )
        )
        return result.rowcount > 0
