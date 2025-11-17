"""
RAG Upload Service - сервис для загрузки и инициализации RAG документов
"""
from __future__ import annotations
from typing import Optional, List
from uuid import UUID, uuid4
import json
import io
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from app.adapters.s3_client import s3_manager
from app.core.config import get_settings
from app.repositories.factory import AsyncRepositoryFactory
from app.models.rag import RAGDocument
from app.models.rag_ingest import Source
from app.services.rag_status_manager import RAGStatusManager
from app.services.rag_event_publisher import RAGEventPublisher
from app.core.logging import get_logger

logger = get_logger(__name__)


class RAGUploadService:
    """Сервис для загрузки RAG документов"""
    
    def __init__(
        self, 
        session: AsyncSession,
        repo_factory: AsyncRepositoryFactory,
        event_publisher: Optional[RAGEventPublisher] = None
    ):
        self.session = session
        self.repo_factory = repo_factory
        self.event_publisher = event_publisher
    
    async def upload_document(
        self,
        file_content: bytes,
        filename: str,
        user_id: UUID,
        content_type: Optional[str] = None,
        name: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> dict:
        """
        Загружает документ в S3 и создаёт записи в БД
        
        Args:
            file_content: Содержимое файла
            filename: Имя файла
            user_id: ID пользователя
            content_type: MIME тип
            name: Отображаемое имя (если отличается от filename)
            tags: Теги документа
            
        Returns:
            Информация о загруженном документе
        """
        # Генерируем ID документа
        doc_id = uuid4()
        doc_name = name or filename or f"Document {doc_id}"
        doc_tags = tags or []
        
        # Подготавливаем S3 ключ
        settings = get_settings()
        s3_key = f"rag/documents/{doc_id}/{filename}"
        
        # Загружаем в S3
        await self._upload_to_s3(file_content, s3_key, settings.S3_BUCKET_RAG)
        
        # Создаём записи в БД
        document = await self._create_document_record(
            doc_id=doc_id,
            filename=filename,
            name=doc_name,
            content_type=content_type,
            size=len(file_content),
            tags=doc_tags,
            s3_key=s3_key,
            user_id=user_id
        )
        
        # Создаём source для ingest pipeline
        await self._create_source_record(
            doc_id=doc_id,
            filename=filename,
            content_type=content_type,
            size=len(file_content),
            s3_key=s3_key
        )
        
        # Инициализируем статусы
        await self._initialize_statuses(doc_id)
        
        await self.session.flush()  # Flush document creation
        
        return {
            "id": str(document.id),
            "status": document.status,
            "message": "File uploaded successfully"
        }
    
    async def _upload_to_s3(self, file_content: bytes, s3_key: str, bucket: str):
        """Загружает файл в S3"""
        # Проверяем/создаём bucket
        client = s3_manager._get_client()
        try:
            client.head_bucket(Bucket=bucket)
        except Exception:
            try:
                client.create_bucket(Bucket=bucket)
            except Exception as e:
                logger.warning(f"Could not create bucket {bucket}: {e}")
        
        # Загружаем файл
        file_obj = io.BytesIO(file_content)
        upload_result = await s3_manager.upload_fileobj(
            bucket=bucket,
            key=s3_key,
            file_obj=file_obj
        )
        
        logger.info(f"File uploaded to S3: bucket={bucket}, key={s3_key}, size={len(file_content)}")
        return upload_result
    
    async def _create_document_record(
        self,
        doc_id: UUID,
        filename: str,
        name: str,
        content_type: Optional[str],
        size: int,
        tags: List[str],
        s3_key: str,
        user_id: UUID
    ) -> RAGDocument:
        """Создаёт запись документа в БД"""
        document = RAGDocument(
            id=doc_id,
            tenant_id=self.repo_factory.tenant_id,
            user_id=user_id,
            filename=filename,
            title=name,
            content_type=content_type,
            size=size,
            tags=tags,
            s3_key_raw=s3_key,
            status="uploaded",
            scope="local"  # Default scope for new documents
        )
        
        self.session.add(document)
        await self.session.flush()  # Для FK references
        
        return document
    
    async def _create_source_record(
        self,
        doc_id: UUID,
        filename: str,
        content_type: Optional[str],
        size: int,
        s3_key: str
    ):
        """Создаёт запись source для ingest pipeline"""
        source = Source(
            source_id=doc_id,
            tenant_id=self.repo_factory.tenant_id,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            meta={
                "filename": filename,
                "content_type": content_type,
                "size": size,
                "s3_key": s3_key
            }
        )
        
        self.session.add(source)
    
    async def _initialize_statuses(self, doc_id: UUID):
        """Инициализирует статусы документа"""
        if not self.event_publisher:
            logger.warning("No event publisher provided, skipping status initialization")
            return
        
        status_manager = RAGStatusManager(
            self.session, 
            self.repo_factory, 
            self.event_publisher
        )
        
        # Получаем embed models тенанта (global + optional extra)
        from sqlalchemy import select
        from app.models.tenant import Tenants
        from app.models.model_registry import ModelRegistry
        
        result = await self.session.execute(
            select(Tenants).where(Tenants.id == self.repo_factory.tenant_id)
        )
        tenant = result.scalar_one_or_none()
        models: list[str] = []
        res_global = await self.session.execute(
            select(ModelRegistry).where((ModelRegistry.is_global == True) & (ModelRegistry.modality == "text"))
        )
        global_embed = res_global.scalars().first()
        if global_embed and global_embed.state in ("active", "archived"):
            models.append(global_embed.model)
        if tenant and tenant.extra_embed_model and tenant.extra_embed_model not in models:
            models.append(tenant.extra_embed_model)
        embed_models = models
        
        # Инициализируем все статусы
        await status_manager.initialize_document_statuses(
            doc_id=doc_id,
            tenant_id=self.repo_factory.tenant_id,
            embed_models=embed_models
        )
        
        logger.info(f"Status nodes initialized for document {doc_id}")
