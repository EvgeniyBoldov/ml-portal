"""
RAG ingest repositories for working with rag_ingest models
"""
from __future__ import annotations
from typing import List, Optional, Dict, Any
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from sqlalchemy.dialects.postgresql import insert

from app.models.rag_ingest import Source, Chunk, EmbStatus
from app.models.model_registry import ModelRegistry
from app.repositories.base import AsyncTenantRepository, AsyncRepository
from app.core.logging import get_logger

logger = get_logger(__name__)


class AsyncSourceRepository(AsyncTenantRepository):
    """Async repository for Source model operations"""
    
    def __init__(self, session: AsyncSession, tenant_id: UUID, user_id: Optional[UUID] = None):
        super().__init__(session, Source, tenant_id, user_id)
    
    async def get_by_id(self, source_id: UUID) -> Optional[Source]:
        """Get source by ID"""
        result = await self.session.execute(
            select(Source).where(
                Source.source_id == source_id,
                Source.tenant_id == self.tenant_id
            )
        )
        return result.scalar_one_or_none()
    
    async def create(self, source_id: UUID, status: str = "uploaded", meta: Dict[str, Any] = None) -> Source:
        """Create new source"""
        source = Source(
            source_id=source_id,
            tenant_id=self.tenant_id,
            status=status,
            meta=meta or {}
        )
        self.session.add(source)
        await self.session.flush()
        return source
    
    async def update_status(self, source_id: UUID, status: str) -> bool:
        """Update source status only if it's different"""
        # First check current status
        result = await self.session.execute(
            select(Source.status).where(
                Source.source_id == source_id,
                Source.tenant_id == self.tenant_id
            )
        )
        current_status = result.scalar_one_or_none()
        
        # Only update if status is different
        if current_status == status:
            return True  # No change needed
        
        result = await self.session.execute(
            update(Source).where(
                Source.source_id == source_id,
                Source.tenant_id == self.tenant_id
            ).values(status=status)
        )
        return result.rowcount > 0
    
    async def list_by_status(self, status: str) -> List[Source]:
        """List sources by status"""
        result = await self.session.execute(
            select(Source).where(
                Source.status == status,
                Source.tenant_id == self.tenant_id
            )
        )
        return result.scalars().all()


class AsyncChunkRepository(AsyncTenantRepository):
    """Async repository for Chunk model operations"""
    
    def __init__(self, session: AsyncSession, tenant_id: UUID, user_id: Optional[UUID] = None):
        super().__init__(session, Chunk, tenant_id, user_id)
    
    async def get_by_source_id(self, source_id: UUID) -> List[Chunk]:
        """Get chunks by source ID"""
        result = await self.session.execute(
            select(Chunk).join(Source).where(
                Source.source_id == source_id,
                Source.tenant_id == self.tenant_id
            )
        )
        return result.scalars().all()
    
    async def bulk_upsert(self, chunks_data: List[Dict[str, Any]]) -> int:
        """Bulk upsert chunks"""
        if not chunks_data:
            return 0
        
        # Prepare data for upsert
        upsert_data = []
        for chunk_data in chunks_data:
            upsert_data.append({
                "chunk_id": chunk_data["chunk_id"],
                "source_id": chunk_data["source_id"],
                "page": chunk_data.get("page"),
                "offset": chunk_data["offset"],
                "length": chunk_data["length"],
                "lang": chunk_data.get("lang"),
                "hash": chunk_data["hash"],
                "meta": chunk_data.get("meta", {})
            })
        
        # Use PostgreSQL UPSERT
        stmt = insert(Chunk).values(upsert_data)
        stmt = stmt.on_conflict_do_update(
            index_elements=['chunk_id'],
            set_={
                'page': stmt.excluded.page,
                'offset': stmt.excluded.offset,
                'length': stmt.excluded.length,
                'lang': stmt.excluded.lang,
                'hash': stmt.excluded.hash,
                'meta': stmt.excluded.meta
            }
        )
        
        result = await self.session.execute(stmt)
        return result.rowcount
    
    async def get_texts_for_chunk_ids(self, source_id: UUID, chunk_ids: List[str]) -> Dict[str, str]:
        """Get texts for specific chunk IDs"""
        if not chunk_ids:
            return {}
        
        result = await self.session.execute(
            select(Chunk).where(
                Chunk.source_id == source_id,
                Chunk.chunk_id.in_(chunk_ids)
            )
        )
        chunks = result.scalars().all()
        
        # Извлекаем тексты из meta поля
        texts = {}
        for chunk in chunks:
            text = ""
            if chunk.meta and isinstance(chunk.meta, dict):
                text = chunk.meta.get('text', '')
            texts[chunk.chunk_id] = text
        
        return texts


class AsyncEmbStatusRepository(AsyncRepository):
    """Async repository for EmbStatus model operations"""
    
    def __init__(self, session: AsyncSession, tenant_id: UUID, user_id: Optional[UUID] = None):
        super().__init__(session, EmbStatus)
        self.tenant_id = tenant_id
        self.user_id = user_id
    
    async def get_by_source_id(self, source_id: UUID) -> List[EmbStatus]:
        """Get embedding statuses by source ID"""
        result = await self.session.execute(
            select(EmbStatus).join(Source).where(
                Source.source_id == source_id,
                Source.tenant_id == self.tenant_id
            )
        )
        return result.scalars().all()
    
    async def create_or_update(self, source_id: UUID, model_alias: str, total_count: int, 
                              model_version: str = None) -> EmbStatus:
        """Create or update embedding status"""
        result = await self.session.execute(
            select(EmbStatus).where(
                EmbStatus.source_id == source_id,
                EmbStatus.model_alias == model_alias
            )
        )
        emb_status = result.scalar_one_or_none()
        
        if emb_status:
            emb_status.total_count = total_count
            emb_status.model_version = model_version
        else:
            emb_status = EmbStatus(
                source_id=source_id,
                model_alias=model_alias,
                total_count=total_count,
                done_count=0,
                model_version=model_version
            )
            self.session.add(emb_status)
        
        await self.session.flush()
        return emb_status
    
    async def update_done_count(self, source_id: UUID, model_alias: str, done_count: int) -> bool:
        """Update done count for embedding status"""
        result = await self.session.execute(
            update(EmbStatus).where(
                EmbStatus.source_id == source_id,
                EmbStatus.model_alias == model_alias
            ).values(done_count=done_count)
        )
        await self.session.commit()
        return result.rowcount > 0
    
    async def is_source_ready(self, source_id: UUID) -> bool:
        """Check if source is ready (all models completed)"""
        emb_statuses = await self.get_by_source_id(source_id)
        if not emb_statuses:
            return False
        
        return all(es.done_count == es.total_count for es in emb_statuses)
    
    async def ready_for_source(self, source_id: UUID) -> bool:
        """Check if source is ready for search (all embeddings completed)"""
        emb_statuses = await self.get_by_source_id(source_id)
        
        if not emb_statuses:
            return False
        
        return all(es.done_count == es.total_count for es in emb_statuses)
    
    async def get_by_source_and_model(self, source_id: UUID, model_alias: str) -> Optional[EmbStatus]:
        """Get embedding status by source ID and model alias"""
        result = await self.session.execute(
            select(EmbStatus).where(
                EmbStatus.source_id == source_id,
                EmbStatus.model_alias == model_alias
            )
        )
        return result.scalar_one_or_none()


class AsyncModelRegistryRepository(AsyncTenantRepository):
    """Async repository for ModelRegistry model operations"""
    
    def __init__(self, session: AsyncSession, tenant_id: UUID, user_id: Optional[UUID] = None):
        super().__init__(session, ModelRegistry, tenant_id, user_id)
    
    async def get_by_alias(self, model_alias: str) -> Optional[ModelRegistry]:
        """Get model registry by model name"""
        result = await self.session.execute(
            select(ModelRegistry).where(ModelRegistry.model == model_alias)
        )
        return result.scalar_one_or_none()
    
    async def create_or_update(self, model_alias: str, model_version: str, dim: int) -> ModelRegistry:
        """Create or update model registry"""
        model_registry = await self.get_by_alias(model_alias)
        
        if model_registry:
            model_registry.version = model_version
            model_registry.vector_dim = dim
        else:
            model_registry = ModelRegistry(
                model=model_alias,
                version=model_version,
                modality="text",  # Default for embedding models
                vector_dim=dim,
                path=f"/models/{model_alias}",  # Default path
                state="active"
            )
            self.session.add(model_registry)
        
        await self.session.flush()
        return model_registry
    
    async def list_all(self) -> List[ModelRegistry]:
        """List all model registries"""
        result = await self.session.execute(select(ModelRegistry))
        return result.scalars().all()
    
    async def get_active_models(self) -> List[ModelRegistry]:
        """Get all active model registries"""
        result = await self.session.execute(
            select(ModelRegistry).where(ModelRegistry.state == 'active')
        )
        return result.scalars().all()