from __future__ import annotations
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, or_, desc, asc
from datetime import datetime, timezone
import uuid

from app.models.rag import RAGDocument, RAGChunk
from app.repositories._base import BaseRepository, AsyncBaseRepository
from app.core.logging import get_logger

logger = get_logger(__name__)

class RAGDocumentsRepository(BaseRepository[RAGDocument]):
    """Enhanced RAG documents repository"""
    
    def __init__(self, session: Session):
        super().__init__(session, RAGDocument)
    
    def create_document(self, filename: str, title: str, user_id: str,
                       content_type: Optional[str] = None, size: Optional[int] = None,
                       tags: Optional[List[str]] = None, s3_key_raw: Optional[str] = None,
                       s3_key_processed: Optional[str] = None) -> RAGDocument:
        """Create a new RAG document"""
        return self.create(
            filename=filename,
            title=title,
            user_id=user_id,
            content_type=content_type,
            size=size,
            tags=tags or [],
            s3_key_raw=s3_key_raw,
            s3_key_processed=s3_key_processed,
            status="uploading"
        )
    
    def get_user_documents(self, user_id: str, status: Optional[str] = None,
                          limit: int = 50, offset: int = 0) -> List[RAGDocument]:
        """Get documents for a user"""
        filters = {'user_id': user_id}
        if status:
            filters['status'] = status
        
        return self.list(filters=filters, order_by='-created_at', limit=limit, offset=offset)
    
    def get_document_by_s3_key(self, s3_key: str) -> Optional[RAGDocument]:
        """Get document by S3 key"""
        stmt = select(RAGDocument).where(
            or_(
                RAGDocument.s3_key_raw == s3_key,
                RAGDocument.s3_key_processed == s3_key
            )
        )
        result = self.session.execute(stmt)
        return result.scalar_one_or_none()
    
    def update_document_status(self, document_id: str, status: str, 
                              error_message: Optional[str] = None) -> Optional[RAGDocument]:
        """Update document status"""
        updates = {'status': status}
        if error_message:
            updates['error_message'] = error_message
        if status == "processed":
            updates['processed_at'] = datetime.now(timezone.utc)
        
        return self.update(document_id, **updates)
    
    def search_documents(self, user_id: str, query: str, status: Optional[str] = None,
                        limit: int = 50) -> List[RAGDocument]:
        """Search documents by title or filename"""
        stmt = select(RAGDocument).where(
            and_(
                RAGDocument.user_id == user_id,
                or_(
                    RAGDocument.title.ilike(f"%{query}%"),
                    RAGDocument.filename.ilike(f"%{query}%")
                )
            )
        )
        
        if status:
            stmt = stmt.where(RAGDocument.status == status)
        
        stmt = stmt.order_by(desc(RAGDocument.created_at)).limit(limit)
        
        result = self.session.execute(stmt)
        return result.scalars().all()
    
    def get_documents_by_tag(self, user_id: str, tag: str, limit: int = 50) -> List[RAGDocument]:
        """Get documents by tag"""
        stmt = select(RAGDocument).where(
            and_(
                RAGDocument.user_id == user_id,
                RAGDocument.tags.contains([tag])
            )
        ).order_by(desc(RAGDocument.created_at)).limit(limit)
        
        result = self.session.execute(stmt)
        return result.scalars().all()
    
    def get_document_stats(self, user_id: str) -> Dict[str, int]:
        """Get document statistics for a user"""
        total = self.count(filters={'user_id': user_id})
        processed = self.count(filters={'user_id': user_id, 'status': 'processed'})
        processing = self.count(filters={'user_id': user_id, 'status': 'processing'})
        failed = self.count(filters={'user_id': user_id, 'status': 'failed'})
        
        return {
            'total': total,
            'processed': processed,
            'processing': processing,
            'failed': failed
        }
    
    def delete_document(self, document_id: str) -> bool:
        """Delete document and all its chunks"""
        document = self.get_by_id(document_id)
        if not document:
            return False
        
        # Delete all chunks first
        chunks_repo = RAGChunksRepository(self.session)
        chunks_repo.delete_document_chunks(document_id)
        
        # Delete document
        return super().delete(document_id)


class RAGChunksRepository(BaseRepository[RAGChunk]):
    """Repository for RAG chunks"""
    
    def __init__(self, session: Session):
        super().__init__(session, RAGChunk)
    
    def create_chunk(self, document_id: str, content: str, chunk_index: int,
                    embedding: Optional[List[float]] = None, vector_id: Optional[str] = None,
                    chunk_metadata: Optional[Dict[str, Any]] = None) -> RAGChunk:
        """Create a new RAG chunk"""
        return self.create(
            document_id=document_id,
            content=content,
            chunk_index=chunk_index,
            embedding=embedding,
            vector_id=vector_id,
            chunk_metadata=chunk_metadata or {}
        )
    
    def get_document_chunks(self, document_id: str, limit: int = 1000) -> List[RAGChunk]:
        """Get all chunks for a document"""
        return self.list(
            filters={'document_id': document_id},
            order_by='chunk_index',
            limit=limit
        )
    
    def get_chunk_by_vector_id(self, vector_id: str) -> Optional[RAGChunk]:
        """Get chunk by vector ID"""
        return self.get_by_field('vector_id', vector_id)
    
    def update_chunk_embedding(self, chunk_id: str, embedding: List[float], 
                              vector_id: Optional[str] = None) -> Optional[RAGChunk]:
        """Update chunk embedding"""
        updates = {'embedding': embedding}
        if vector_id:
            updates['vector_id'] = vector_id
        
        return self.update(chunk_id, **updates)
    
    def get_chunks_without_embeddings(self, limit: int = 100) -> List[RAGChunk]:
        """Get chunks that don't have embeddings yet"""
        stmt = select(RAGChunk).where(
            RAGChunk.embedding.is_(None)
        ).limit(limit)
        
        result = self.session.execute(stmt)
        return result.scalars().all()
    
    def get_chunks_by_metadata(self, document_id: str, metadata_key: str, 
                              metadata_value: Any) -> List[RAGChunk]:
        """Get chunks by metadata key-value pair"""
        stmt = select(RAGChunk).where(
            and_(
                RAGChunk.document_id == document_id,
                RAGChunk.chunk_metadata[metadata_key].astext == str(metadata_value)
            )
        )
        
        result = self.session.execute(stmt)
        return result.scalars().all()
    
    def delete_document_chunks(self, document_id: str) -> int:
        """Delete all chunks for a document"""
        stmt = select(RAGChunk).where(RAGChunk.document_id == document_id)
        result = self.session.execute(stmt)
        chunks = result.scalars().all()
        
        for chunk in chunks:
            self.session.delete(chunk)
        
        self.session.flush()
        return len(chunks)
    
    def count_document_chunks(self, document_id: str) -> int:
        """Count chunks for a document"""
        return self.count(filters={'document_id': document_id})
    
    def search_chunks(self, document_id: str, query: str, limit: int = 50) -> List[RAGChunk]:
        """Search chunks by content"""
        stmt = select(RAGChunk).where(
            and_(
                RAGChunk.document_id == document_id,
                RAGChunk.content.ilike(f"%{query}%")
            )
        ).order_by(asc(RAGChunk.chunk_index)).limit(limit)
        
        result = self.session.execute(stmt)
        return result.scalars().all()


# Async versions
class AsyncRAGDocumentsRepository(AsyncBaseRepository[RAGDocument]):
    """Async RAG documents repository"""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, RAGDocument)
    
    async def create_document(self, filename: str, title: str, user_id: str,
                             content_type: Optional[str] = None, size: Optional[int] = None,
                             tags: Optional[List[str]] = None, s3_key_raw: Optional[str] = None,
                             s3_key_processed: Optional[str] = None) -> RAGDocument:
        """Create a new RAG document"""
        return await self.create(
            filename=filename,
            title=title,
            user_id=user_id,
            content_type=content_type,
            size=size,
            tags=tags or [],
            s3_key_raw=s3_key_raw,
            s3_key_processed=s3_key_processed,
            status="uploading"
        )
    
    async def get_user_documents(self, user_id: str, status: Optional[str] = None,
                                limit: int = 50, offset: int = 0) -> List[RAGDocument]:
        """Get documents for a user"""
        filters = {'user_id': user_id}
        if status:
            filters['status'] = status
        
        return await self.list(filters=filters, order_by='-created_at', limit=limit, offset=offset)
    
    async def update_document_status(self, document_id: str, status: str, 
                                    error_message: Optional[str] = None) -> Optional[RAGDocument]:
        """Update document status"""
        updates = {'status': status}
        if error_message:
            updates['error_message'] = error_message
        if status == "processed":
            updates['processed_at'] = datetime.now(timezone.utc)
        
        return await self.update(document_id, **updates)


class AsyncRAGChunksRepository(AsyncBaseRepository[RAGChunk]):
    """Async RAG chunks repository"""
    
    def __init__(self, session: AsyncSession):
        super().__init__(session, RAGChunk)
    
    async def create_chunk(self, document_id: str, content: str, chunk_index: int,
                          embedding: Optional[List[float]] = None, vector_id: Optional[str] = None,
                          chunk_metadata: Optional[Dict[str, Any]] = None) -> RAGChunk:
        """Create a new RAG chunk"""
        return await self.create(
            document_id=document_id,
            content=content,
            chunk_index=chunk_index,
            embedding=embedding,
            vector_id=vector_id,
            chunk_metadata=chunk_metadata or {}
        )
    
    async def get_document_chunks(self, document_id: str, limit: int = 1000) -> List[RAGChunk]:
        """Get all chunks for a document"""
        return await self.list(
            filters={'document_id': document_id},
            order_by='chunk_index',
            limit=limit
        )
    
    async def update_chunk_embedding(self, chunk_id: str, embedding: List[float], 
                                    vector_id: Optional[str] = None) -> Optional[RAGChunk]:
        """Update chunk embedding"""
        updates = {'embedding': embedding}
        if vector_id:
            updates['vector_id'] = vector_id
        
        return await self.update(chunk_id, **updates)


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
