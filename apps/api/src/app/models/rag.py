"""
RAG Document Model
"""
from sqlalchemy import Column, String, DateTime, Integer, JSON, Text, Index
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime, timezone
import uuid

from app.models.base import Base


class RAGDocument(Base):
    """RAG документ"""
    __tablename__ = "rag_documents"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    filename = Column(String(255), nullable=False)
    title = Column(String(255), nullable=False)
    status = Column(String(50), nullable=False, default="uploading")  # uploading, processing, processed, failed, archived
    
    # Метаданные
    user_id = Column(UUID(as_uuid=False), nullable=False, index=True)
    content_type = Column(String(100), nullable=True)
    size = Column(Integer, nullable=True)  # Размер в байтах
    tags = Column(JSON, nullable=True, default=list)  # Список тегов
    
    # S3 ключи
    s3_key_raw = Column(String(500), nullable=True)  # Ключ для сырого файла
    s3_key_processed = Column(String(500), nullable=True)  # Ключ для обработанного файла
    
    # Временные метки
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Обработка
    processed_at = Column(DateTime(timezone=True), nullable=True)
    error_message = Column(Text, nullable=True)
    
    # Индексы
    __table_args__ = (
        Index('idx_rag_documents_user_status', 'user_id', 'status'),
        Index('idx_rag_documents_created_at', 'created_at'),
        # GIN индекс для JSON поля tags (создается отдельно в миграциях)
    )
    
    def __repr__(self):
        return f"<RAGDocument(id='{self.id}', filename='{self.filename}', status='{self.status}')>"
    
    def to_dict(self):
        """Преобразовать в словарь"""
        return {
            "id": self.id,
            "filename": self.filename,
            "title": self.title,
            "status": self.status,
            "user_id": self.user_id,
            "content_type": self.content_type,
            "size": self.size,
            "tags": self.tags or [],
            "s3_key_raw": self.s3_key_raw,
            "s3_key_processed": self.s3_key_processed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "error_message": self.error_message
        }


class RAGChunk(Base):
    """RAG чанк документа"""
    __tablename__ = "rag_chunks"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=lambda: str(uuid.uuid4()))
    document_id = Column(UUID(as_uuid=False), nullable=False, index=True)
    content = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False, default=0)
    
    # Векторные данные
    embedding = Column(JSON, nullable=True)  # Векторное представление
    vector_id = Column(String(255), nullable=True)  # ID в Qdrant
    
    # Метаданные
    chunk_metadata = Column(JSON, nullable=True, default=dict)
    
    # Временные метки
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    
    # Индексы
    __table_args__ = (
        Index('idx_rag_chunks_document_id', 'document_id'),
        Index('idx_rag_chunks_vector_id', 'vector_id'),
    )
    
    def __repr__(self):
        return f"<RAGChunk(id='{self.id}', document_id='{self.document_id}', chunk_index={self.chunk_index})>"
    
    def to_dict(self):
        """Преобразовать в словарь"""
        return {
            "id": self.id,
            "document_id": self.document_id,
            "content": self.content,
            "chunk_index": self.chunk_index,
            "embedding": self.embedding,
            "vector_id": self.vector_id,
            "metadata": self.chunk_metadata or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }