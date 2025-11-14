"""
Documents repository for RAG document management
"""
from __future__ import annotations
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, asc
from datetime import datetime, timezone
import uuid

from app.models.rag import RAGDocument, RAGChunk
from app.repositories.base import AsyncTenantRepository
from app.core.logging import get_logger

logger = get_logger(__name__)


class AsyncRAGDocumentsRepository(AsyncTenantRepository[RAGDocument]):
    """Async RAG documents repository with tenant isolation"""
    
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID, user_id: Optional[uuid.UUID] = None):
        super().__init__(session, RAGDocument, tenant_id, user_id)
    
    async def create_document(self, user_id: uuid.UUID, filename: str, **kwargs) -> RAGDocument:
        """Create a new RAG document"""
        return await self.create(
            self.tenant_id,
            user_id=user_id,
            filename=filename,
            **kwargs
        )
    
    async def get_user_documents(self, user_id: uuid.UUID, status: Optional[str] = None,
                                search: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[RAGDocument]:
        """Get documents for a specific user with filtering"""
        query = select(RAGDocument).where(
            and_(
                RAGDocument.tenant_id == self.tenant_id,
                RAGDocument.user_id == user_id
            )
        )
        
        if status:
            query = query.where(RAGDocument.status == status)
        
        if search:
            query = query.where(
                or_(
                    RAGDocument.filename.ilike(f"%{search}%"),
                    RAGDocument.title.ilike(f"%{search}%")
                )
            )
        
        query = query.order_by(desc(RAGDocument.created_at))
        query = query.offset(offset).limit(limit)
        
        result = await self.session.execute(query)
        return result.scalars().all()
    
    async def count_user_documents(self, user_id: uuid.UUID, status: Optional[str] = None,
                                 search: Optional[str] = None) -> int:
        """Count documents for a specific user with filtering"""
        query = select(func.count(RAGDocument.id)).where(
            and_(
                RAGDocument.tenant_id == self.tenant_id,
                RAGDocument.user_id == user_id
            )
        )
        
        if status:
            query = query.where(RAGDocument.status == status)
        
        if search:
            query = query.where(
                or_(
                    RAGDocument.filename.ilike(f"%{search}%"),
                    RAGDocument.title.ilike(f"%{search}%")
                )
            )
        
        result = await self.session.execute(query)
        return result.scalar()
    
    async def get_tenant_documents(self, status: Optional[str] = None,
                                  search: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[RAGDocument]:
        """Get all documents for the tenant with filtering (shared across all tenant users)"""
        query = select(RAGDocument).where(RAGDocument.tenant_id == self.tenant_id)
        
        if status:
            query = query.where(RAGDocument.status == status)
        
        if search:
            query = query.where(
                or_(
                    RAGDocument.filename.ilike(f"%{search}%"),
                    RAGDocument.title.ilike(f"%{search}%")
                )
            )
        
        query = query.order_by(desc(RAGDocument.created_at))
        query = query.offset(offset).limit(limit)
        
        result = await self.session.execute(query)
        return result.scalars().all()
    
    async def count_tenant_documents(self, status: Optional[str] = None, search: Optional[str] = None) -> int:
        """Count all documents for the tenant with filtering"""
        query = select(func.count(RAGDocument.id)).where(RAGDocument.tenant_id == self.tenant_id)
        
        if status:
            query = query.where(RAGDocument.status == status)
        
        if search:
            query = query.where(
                or_(
                    RAGDocument.filename.ilike(f"%{search}%"),
                    RAGDocument.title.ilike(f"%{search}%")
                )
            )
        
        result = await self.session.execute(query)
        return result.scalar()


class AsyncRAGChunksRepository(AsyncTenantRepository[RAGChunk]):
    """Async RAG chunks repository with tenant isolation"""
    
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID, user_id: Optional[uuid.UUID] = None):
        super().__init__(session, RAGChunk, tenant_id, user_id)
    
    async def get_by_document_id(self, document_id: uuid.UUID) -> List[RAGChunk]:
        """Get chunks by document ID"""
        result = await self.session.execute(
            select(RAGChunk).where(RAGChunk.document_id == document_id)
        )
        return result.scalars().all()
    
    async def get_by_chunk_index(self, document_id: uuid.UUID, chunk_index: int) -> Optional[RAGChunk]:
        """Get chunk by document ID and index"""
        result = await self.session.execute(
            select(RAGChunk).where(
                and_(
                    RAGChunk.document_id == document_id,
                    RAGChunk.chunk_idx == chunk_index
                )
            )
        )
        return result.scalar_one_or_none()