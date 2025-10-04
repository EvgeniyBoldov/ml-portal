"""
RAG Document Model with RBAC and Scope
"""
from sqlalchemy import Column, String, DateTime, Integer, JSON, Text, Index, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
import uuid
import enum

from app.models.base import Base


class DocumentScope(str, enum.Enum):
    """Scope of document visibility"""
    LOCAL = "local"
    GLOBAL = "global"


class DocumentStatus(str, enum.Enum):
    """Status of document processing"""
    UPLOADING = "uploading"
    PROCESSING = "processing" 
    PROCESSED = "processed"
    FAILED = "failed"
    ARCHIVED = "archived"


class RAGDocument(Base):
    """RAG документ с поддержкой scope и RBAC"""
    __tablename__ = "rag_documents"
    
    # Основные поля
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename = Column(String(255), nullable=False)
    title = Column(String(255), nullable=False)
    status = Column(
        SQLEnum(DocumentStatus), 
        nullable=False, 
        default=DocumentStatus.UPLOADING,
        comment="Processing status"
    )
    
    # Видимость и принадлежность
    scope = Column(
        SQLEnum(DocumentScope),
        nullable=False,
        default=DocumentScope.LOCAL,
        comment="Document scope: local (tenant-only) or global (all tenants)"
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        nullable=True,
        comment="Tenant ID (null for global documents)"
    )
    
    # Метаданные
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    content_type = Column(String(100), nullable=True)
    size = Column(Integer, nullable=True)  # Размер в байтах
    tags = Column(JSON, nullable=True, default=list)  # Список тегов
    
    # Версионирование для глобальных документов
    global_version = Column(Integer, nullable=True, comment="Version for global documents")
    published_at = Column(DateTime(timezone=True), nullable=True)
    published_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        nullable=True,
        comment="User who published the global document"
    )
    
    # S3 ключи с учетом scope
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
        Index('idx_rag_documents_tenant_scope', 'tenant_id', 'scope'),
        Index('idx_rag_documents_scope_status', 'scope', 'status'),
        Index('idx_rag_documents_created_at', 'created_at'),
        Index('idx_rag_documents_global_version', 'global_version'),
        # Композитный индекс для поиска глобальных документов
        Index('idx_rag_documents_scope_tenant_lookup', 'scope', 'tenant_id'),
    )
    
    def __repr__(self):
        return f"<RAGDocument(id='{self.id}', filename='{self.filename}', scope='{self.scope.value}')>"
    
    def to_dict(self):
        """Преобразовать в словарь"""
        return {
            "id": str(self.id),
            "filename": self.filename,
            "title": self.title,
            "status": self.status.value,
            "scope": self.scope.value,
            "tenant_id": str(self.tenant_id) if self.tenant_id else None,
            "user_id": str(self.user_id),
            "content_type": self.content_type,
            "size": self.size,
            "tags": self.tags or [],
            "global_version": self.global_version,
            "published_at": self.published_at.isoformat() if self.published_at else None,
            "published_by": str(self.published_by) if self.published_by else None,
            "s3_key_raw": self.s3_key_raw,
            "s3_key_processed": self.s3_key_processed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
            "error_message": self.error_message
        }


class RAGChunk(Base):
    """RAG чанк документа с метаданными scope"""
    __tablename__ = "rag_chunks"
    
    # Основные поля
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    content = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False, default=0)
    
    # Унаследованные метаданные из документа
    scope = Column(
        SQLEnum(DocumentScope),
        nullable=False,
        comment="Inherited from document scope"
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), 
        nullable=True,
        comment="Tenant ID (inherited from document)"
    )
    
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
        Index('idx_rag_chunks_tenant_scope', 'tenant_id', 'scope'),
        Index('idx_rag_chunks_created_at', 'created_at'),
    )
    
    def __repr__(self):
        return f"<RAGChunk(id='{self.id}', document_id='{self.document_id}', scope='{self.scope.value}')>"
    
    def to_dict(self):
        """Преобразовать в словарь"""
        return {
            "id": str(self.id),
            "document_id": str(self.document_id),
            "content": self.content,
            "chunk_index": self.chunk_index,
            "scope": self.scope.value,
            "tenant_id": str(self.tenant_id) if self.tenant_id else None,
            "embedding": self.embedding,
            "vector_id": self.vector_id,
            "metadata": self.chunk_metadata or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }

    @classmethod
    def from_document(cls, document: RAGDocument) -> 'RAGChunk':
        """Создать чанк с унаследованными метаданными от документа"""
        return cls(
            document_id=document.id,
            scope=document.scope,
            tenant_id=document.tenant_id
        )