"""
RAG repositories for document and chunk management
"""
from __future__ import annotations
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc
from repositories.base import TenantRepository, AsyncTenantRepository
from models.rag import RAGDocument, RAGChunk
import uuid


def create_rag_documents_repository(session: Session, tenant_id: uuid.UUID = None) -> RAGDocumentsRepository:
    """Create RAG documents repository"""
    return RAGDocumentsRepository(session, tenant_id or uuid.uuid4())


def create_rag_chunks_repository(session: Session, tenant_id: uuid.UUID = None) -> RAGChunksRepository:
    """Create RAG chunks repository"""
    return RAGChunksRepository(session, tenant_id or uuid.uuid4())


class RAGDocumentsRepository(TenantRepository[RAGDocument]):
    """Repository for RAG documents"""
    
    def __init__(self, session: Session, tenant_id: uuid.UUID):
        super().__init__(session, tenant_id)
        self.model = RAGDocument
    
    def get_by_filename(self, filename: str) -> Optional[RAGDocument]:
        """Get document by filename"""
        return self.session.query(RAGDocument).filter(
            RAGDocument.filename == filename
        ).first()
    
    def get_by_status(self, status: str) -> List[RAGDocument]:
        """Get documents by status"""
        return self.session.query(RAGDocument).filter(
            RAGDocument.status == status
        ).all()


class RAGChunksRepository(TenantRepository[RAGChunk]):
    """Repository for RAG chunks"""
    
    def __init__(self, session: Session, tenant_id: uuid.UUID):
        super().__init__(session, tenant_id)
        self.model = RAGChunk
    
    def get_by_document_id(self, document_id: uuid.UUID) -> List[RAGChunk]:
        """Get chunks by document ID"""
        return self.session.query(RAGChunk).filter(
            RAGChunk.document_id == document_id
        ).all()
    
    def get_by_chunk_index(self, document_id: uuid.UUID, chunk_index: int) -> Optional[RAGChunk]:
        """Get chunk by document ID and index"""
        return self.session.query(RAGChunk).filter(
            RAGChunk.document_id == document_id,
            RAGChunk.chunk_index == chunk_index
        ).first()


class AsyncRAGDocumentsRepository(AsyncTenantRepository[RAGDocument]):
    """Async repository for RAG documents"""
    
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID, user_id: Optional[uuid.UUID] = None):
        super().__init__(session, RAGDocument, tenant_id, user_id)
    
    async def create_document(self, user_id: uuid.UUID, filename: str, **kwargs) -> RAGDocument:
        """Create a new RAG document"""
        return await self.create(
            tenant_id=self.tenant_id,
            user_id=user_id,
            filename=filename,
            **kwargs
        )
    
    async def get_user_documents(self, user_id: uuid.UUID, status: Optional[str] = None,
                                search: Optional[str] = None, limit: int = 50, offset: int = 0) -> List[RAGDocument]:
        """Get documents for a specific user with filtering"""
        filters = {'user_id': user_id}
        
        if status:
            filters['status'] = status
        
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
        
        result = await self.session.execute(query)
        return len(result.scalars().all())


class AsyncRAGChunksRepository(AsyncTenantRepository[RAGChunk]):
    """Async repository for RAG chunks"""
    
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID, user_id: Optional[uuid.UUID] = None):
        super().__init__(session, RAGChunk, tenant_id, user_id)


def create_async_rag_documents_repository(session: AsyncSession, tenant_id: uuid.UUID = None) -> AsyncRAGDocumentsRepository:
    """Create async RAG documents repository"""
    return AsyncRAGDocumentsRepository(session, tenant_id or uuid.uuid4())


def create_async_rag_chunks_repository(session: AsyncSession, tenant_id: uuid.UUID = None) -> AsyncRAGChunksRepository:
    """Create async RAG chunks repository"""
    return AsyncRAGChunksRepository(session, tenant_id or uuid.uuid4())
