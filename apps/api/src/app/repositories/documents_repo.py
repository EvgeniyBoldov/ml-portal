"""
RAG Documents repository with tenant isolation and production-grade features
"""
from __future__ import annotations
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, asc
from datetime import datetime, timezone
import uuid

from app.models.analyze import AnalysisDocuments  # Using the correct model
from app.repositories.base import TenantRepository, AsyncTenantRepository
from app.core.logging import get_logger

logger = get_logger(__name__)


class RAGDocumentsRepository(TenantRepository[AnalysisDocuments]):
    """RAG Documents repository with tenant isolation"""
    
    def __init__(self, session: Session, tenant_id: uuid.UUID, user_id: Optional[uuid.UUID] = None):
        super().__init__(session, AnalysisDocuments, tenant_id, user_id)
    
    def create_document(self, tenant_id: uuid.UUID, uploaded_by: uuid.UUID, 
                      filename: str, title: Optional[str] = None,
                      content_type: Optional[str] = None, size: Optional[int] = None,
                      tags: Optional[List[str]] = None, url_file: Optional[str] = None,
                      status: str = "uploading") -> AnalysisDocuments:
        """Create a new RAG document"""
        return self.create(
            tenant_id=self.tenant_id,
            uploaded_by=uploaded_by,
            filename=filename,
            title=title or filename,
            content_type=content_type,
            size=size,
            tags=tags or [],
            url_file=url_file,
            status=status
        )
    
    def get_user_documents(self, tenant_id: uuid.UUID, uploaded_by: uuid.UUID,
                          status: Optional[str] = None, limit: int = 50, 
                          cursor: Optional[str] = None) -> Tuple[List[AnalysisDocuments], Optional[str]]:
        """Get documents for a user with cursor pagination"""
        filters = {'uploaded_by': uploaded_by}
        if status:
            filters['status'] = status
        
        return self.list(filters=filters, order_by='-created_at', limit=limit, cursor=cursor)
    
    def get_document_by_url(self, tenant_id: uuid.UUID, url_file: str) -> Optional[AnalysisDocuments]:
        """Get document by URL file"""
        filters = {'url_file': url_file}
        entities, _ = self.list(filters=filters, limit=1)
        return entities[0] if entities else None
    
    def update_document_status(self, tenant_id: uuid.UUID, document_id: uuid.UUID, 
                              status: str, expected_version: int, 
                              error_message: Optional[str] = None) -> Optional[AnalysisDocuments]:
        """Update document status with optimistic locking"""
        updates = {'status': status}
        if error_message:
            updates['error_message'] = error_message
        if status == "processed":
            updates['processed_at'] = datetime.now(timezone.utc)
        
        return self.update(document_id, expected_version=expected_version, **updates)
    
    def search_documents(self, tenant_id: uuid.UUID, uploaded_by: uuid.UUID, 
                        query: str, status: Optional[str] = None,
                        limit: int = 50) -> List[AnalysisDocuments]:
        """Search documents by title or filename"""
        stmt = select(AnalysisDocuments).where(
            and_(
                AnalysisDocuments.tenant_id == tenant_id,
                AnalysisDocuments.uploaded_by == uploaded_by,
                or_(
                    AnalysisDocuments.title.ilike(f"%{query}%"),
                    AnalysisDocuments.filename.ilike(f"%{query}%")
                )
            )
        )
        
        if status:
            stmt = stmt.where(AnalysisDocuments.status == status)
        
        stmt = stmt.order_by(desc(AnalysisDocuments.created_at)).limit(limit)
        
        result = self.session.execute(stmt)
        return result.scalars().all()
    
    def get_documents_by_tag(self, tenant_id: uuid.UUID, uploaded_by: uuid.UUID, 
                            tag: str, limit: int = 50) -> List[AnalysisDocuments]:
        """Get documents by tag"""
        stmt = select(AnalysisDocuments).where(
            and_(
                AnalysisDocuments.tenant_id == tenant_id,
                AnalysisDocuments.uploaded_by == uploaded_by,
                AnalysisDocuments.tags.contains([tag])
            )
        ).order_by(desc(AnalysisDocuments.created_at)).limit(limit)
        
        result = self.session.execute(stmt)
        return result.scalars().all()
    
    def get_document_stats(self, tenant_id: uuid.UUID, uploaded_by: uuid.UUID) -> Dict[str, int]:
        """Get document statistics for a user"""
        total = self.count(filters={'uploaded_by': uploaded_by})
        processed = self.count(filters={'uploaded_by': uploaded_by, 'status': 'processed'})
        processing = self.count(filters={'uploaded_by': uploaded_by, 'status': 'processing'})
        failed = self.count(filters={'uploaded_by': uploaded_by, 'status': 'failed'})
        
        return {
            'total': total,
            'processed': processed,
            'processing': processing,
            'failed': failed
        }
    
    def upsert_document_by_url(self, tenant_id: uuid.UUID, uploaded_by: uuid.UUID,
                              url_file: str, **kwargs) -> AnalysisDocuments:
        """Upsert document based on URL file"""
        unique_fields = {'url_file': url_file}
        return self.upsert(unique_fields, uploaded_by=uploaded_by, **kwargs)


class RAGChunksRepository(TenantRepository):
    """RAG Chunks repository with tenant isolation"""
    
    def __init__(self, session: Session, tenant_id: uuid.UUID, user_id: Optional[uuid.UUID] = None):
        from app.models.analyze import AnalysisChunks
        super().__init__(session, AnalysisChunks, tenant_id, user_id)
    
    def create_chunk(self, tenant_id: uuid.UUID, document_id: uuid.UUID, 
                    content: str, chunk_idx: int,
                    embedding: Optional[List[float]] = None, vector_id: Optional[str] = None,
                    meta: Optional[Dict[str, Any]] = None) -> Any:
        """Create a new RAG chunk"""
        return self.create(
            tenant_id=self.tenant_id,
            document_id=document_id,
            content=content,
            chunk_idx=chunk_idx,
            embedding=embedding,
            vector_id=vector_id,
            meta=meta or {}
        )
    
    def get_document_chunks(self, tenant_id: uuid.UUID, document_id: uuid.UUID, 
                           limit: int = 1000, cursor: Optional[str] = None) -> Tuple[List[Any], Optional[str]]:
        """Get all chunks for a document with cursor pagination"""
        filters = {'document_id': document_id}
        return self.list(filters=filters, order_by='chunk_idx', limit=limit, cursor=cursor)
    
    def get_chunk_by_vector_id(self, tenant_id: uuid.UUID, vector_id: str) -> Optional[Any]:
        """Get chunk by vector ID"""
        filters = {'vector_id': vector_id}
        entities, _ = self.list(filters=filters, limit=1)
        return entities[0] if entities else None
    
    def update_chunk_embedding(self, tenant_id: uuid.UUID, chunk_id: uuid.UUID, 
                              embedding: List[float], expected_version: int,
                              vector_id: Optional[str] = None) -> Optional[Any]:
        """Update chunk embedding with optimistic locking"""
        updates = {'embedding': embedding}
        if vector_id:
            updates['vector_id'] = vector_id
        
        return self.update(chunk_id, expected_version=expected_version, **updates)
    
    def get_chunks_without_embeddings(self, tenant_id: uuid.UUID, limit: int = 100) -> List[Any]:
        """Get chunks that don't have embeddings yet"""
        filters = {'embedding': None}
        entities, _ = self.list(filters=filters, limit=limit)
        return entities
    
    def bulk_create_chunks(self, tenant_id: uuid.UUID, chunks_data: List[Dict[str, Any]]) -> List[Any]:
        """Bulk create chunks"""
        return self.bulk_create(chunks_data)
    
    def delete_document_chunks(self, tenant_id: uuid.UUID, document_id: uuid.UUID) -> int:
        """Delete all chunks for a document"""
        from sqlalchemy import delete
        from app.models.analyze import AnalysisChunks
        
        delete_stmt = delete(AnalysisChunks).where(
            and_(
                AnalysisChunks.tenant_id == tenant_id,
                AnalysisChunks.document_id == document_id
            )
        )
        result = self.session.execute(delete_stmt)
        return result.rowcount


# Async versions
class AsyncRAGDocumentsRepository(AsyncTenantRepository[AnalysisDocuments]):
    """Async RAG Documents repository with tenant isolation"""
    
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID, user_id: Optional[uuid.UUID] = None):
        super().__init__(session, AnalysisDocuments, tenant_id, user_id)
    
    async def create_document(self, tenant_id: uuid.UUID, uploaded_by: uuid.UUID, 
                             filename: str, title: Optional[str] = None,
                             content_type: Optional[str] = None, size: Optional[int] = None,
                             tags: Optional[List[str]] = None, url_file: Optional[str] = None,
                             status: str = "uploading") -> AnalysisDocuments:
        """Create a new RAG document"""
        return await self.create(
            tenant_id=self.tenant_id,
            uploaded_by=uploaded_by,
            filename=filename,
            title=title or filename,
            content_type=content_type,
            size=size,
            tags=tags or [],
            url_file=url_file,
            status=status
        )
    
    async def get_user_documents(self, tenant_id: uuid.UUID, uploaded_by: uuid.UUID,
                                status: Optional[str] = None, limit: int = 50, 
                                cursor: Optional[str] = None) -> Tuple[List[AnalysisDocuments], Optional[str]]:
        """Get documents for a user with cursor pagination"""
        filters = {'uploaded_by': uploaded_by}
        if status:
            filters['status'] = status
        
        return await self.list(filters=filters, order_by='-created_at', limit=limit, cursor=cursor)
    
    async def update_document_status(self, tenant_id: uuid.UUID, document_id: uuid.UUID, 
                                   status: str, expected_version: int, 
                                   error_message: Optional[str] = None) -> Optional[AnalysisDocuments]:
        """Update document status with optimistic locking"""
        updates = {'status': status}
        if error_message:
            updates['error_message'] = error_message
        if status == "processed":
            updates['processed_at'] = datetime.now(timezone.utc)
        
        return await self.update(document_id, expected_version=expected_version, **updates)


class AsyncRAGChunksRepository(AsyncTenantRepository):
    """Async RAG Chunks repository with tenant isolation"""
    
    def __init__(self, session: AsyncSession, tenant_id: uuid.UUID, user_id: Optional[uuid.UUID] = None):
        from app.models.analyze import AnalysisChunks
        super().__init__(session, AnalysisChunks, tenant_id, user_id)
    
    async def create_chunk(self, tenant_id: uuid.UUID, document_id: uuid.UUID, 
                          content: str, chunk_idx: int,
                          embedding: Optional[List[float]] = None, vector_id: Optional[str] = None,
                          meta: Optional[Dict[str, Any]] = None) -> Any:
        """Create a new RAG chunk"""
        return await self.create(
            tenant_id=self.tenant_id,
            document_id=document_id,
            content=content,
            chunk_idx=chunk_idx,
            embedding=embedding,
            vector_id=vector_id,
            meta=meta or {}
        )
    
    async def get_document_chunks(self, tenant_id: uuid.UUID, document_id: uuid.UUID, 
                                 limit: int = 1000, cursor: Optional[str] = None) -> Tuple[List[Any], Optional[str]]:
        """Get all chunks for a document with cursor pagination"""
        filters = {'document_id': document_id}
        return await self.list(filters=filters, order_by='chunk_idx', limit=limit, cursor=cursor)
    
    async def bulk_create_chunks(self, tenant_id: uuid.UUID, chunks_data: List[Dict[str, Any]]) -> List[Any]:
        """Bulk create chunks"""
        return await self.bulk_create(chunks_data)


# Factory functions
def create_rag_documents_repository(session: Session) -> RAGDocumentsRepository:
    """Create RAG documents repository"""
    return RAGDocumentsRepository(session)

def create_rag_chunks_repository(session: Session) -> RAGChunksRepository:
    """Create RAG chunks repository"""
    return RAGChunksRepository(session)

def create_async_rag_documents_repository(session: AsyncSession) -> AsyncRAGDocumentsRepository:
    """Create async RAG documents repository"""
    return AsyncRAGDocumentsRepository(session)

def create_async_rag_chunks_repository(session: AsyncSession) -> AsyncRAGChunksRepository:
    """Create async RAG chunks repository"""
    return AsyncRAGChunksRepository(session)
