"""
RAG repositories for document and chunk management
"""
from __future__ import annotations
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from app.repositories.base import TenantRepository
from app.models.rag import RAGDocument, RAGChunk
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


class AsyncRAGDocumentsRepository(RAGDocumentsRepository):
    """Async repository for RAG documents"""
    pass


class AsyncRAGChunksRepository(RAGChunksRepository):
    """Async repository for RAG chunks"""
    pass


def create_async_rag_documents_repository(session: Session, tenant_id: uuid.UUID = None) -> AsyncRAGDocumentsRepository:
    """Create async RAG documents repository"""
    return AsyncRAGDocumentsRepository(session, tenant_id or uuid.uuid4())


def create_async_rag_chunks_repository(session: Session, tenant_id: uuid.UUID = None) -> AsyncRAGChunksRepository:
    """Create async RAG chunks repository"""
    return AsyncRAGChunksRepository(session, tenant_id or uuid.uuid4())
