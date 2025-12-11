"""
Model Registry Repository for database operations
"""
from __future__ import annotations
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, update
from sqlalchemy.orm import selectinload
from app.models.model_registry import ModelRegistry, ModelType, ModelStatus
from app.models.tenant import Tenants
from app.core.logging import get_logger
import uuid

logger = get_logger(__name__)


class AsyncModelRegistryRepository:
    """Async repository for model registry operations"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def list_all(
        self, 
        filters: Optional[Dict[str, Any]] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[ModelRegistry]:
        """List all models with optional filtering"""
        query = select(ModelRegistry)
        
        if filters:
            if filters.get('status'):
                query = query.where(ModelRegistry.status == filters['status'])
            if filters.get('type'):
                query = query.where(ModelRegistry.type == filters['type'])
            if filters.get('search'):
                search_term = f"%{filters['search']}%"
                query = query.where(
                    or_(
                        ModelRegistry.alias.ilike(search_term),
                        ModelRegistry.provider_model_name.ilike(search_term),
                        ModelRegistry.name.ilike(search_term)
                    )
                )
        
        query = query.order_by(ModelRegistry.alias).offset(offset).limit(limit)
        
        result = await self.session.execute(query)
        return result.scalars().all()
    
    async def get_by_id(self, model_id: uuid.UUID) -> Optional[ModelRegistry]:
        """Get model by ID"""
        result = await self.session.execute(
            select(ModelRegistry).where(ModelRegistry.id == model_id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_alias(self, alias: str) -> Optional[ModelRegistry]:
        """Get model by alias"""
        result = await self.session.execute(
            select(ModelRegistry).where(ModelRegistry.alias == alias)
        )
        return result.scalar_one_or_none()
    
    # Deprecated alias for backward compatibility during refactor
    async def get_by_model(self, model: str) -> Optional[ModelRegistry]:
        return await self.get_by_alias(model)

    async def create(self, data: Dict[str, Any]) -> ModelRegistry:
        """Create a new model registry entry"""
        model_registry = ModelRegistry(**data)
        self.session.add(model_registry)
        await self.session.flush()
        await self.session.refresh(model_registry)
        return model_registry
    
    async def update(self, model_id: uuid.UUID, data: Dict[str, Any]) -> Optional[ModelRegistry]:
        """Update model registry entry"""
        # Remove None values
        update_data = {k: v for k, v in data.items() if v is not None}
        
        if not update_data:
            return await self.get_by_id(model_id)
        
        await self.session.execute(
            update(ModelRegistry)
            .where(ModelRegistry.id == model_id)
            .values(**update_data)
        )
        
        return await self.get_by_id(model_id)
    
    async def delete(self, model_id: uuid.UUID) -> bool:
        """Delete model registry entry"""
        result = await self.session.execute(
            select(ModelRegistry).where(ModelRegistry.id == model_id)
        )
        model = result.scalar_one_or_none()
        
        if not model:
            return False
        
        await self.session.delete(model)
        return True
    
    async def count_tenants_using(self, alias: str) -> int:
        """Count tenants using a specific model as embedding"""
        result = await self.session.execute(
            select(func.count(Tenants.id)).where(Tenants.embedding_model_alias == alias)
        )
        return result.scalar() or 0
    
    async def get_tenants_by_model(self, alias: str) -> List[Tenants]:
        """Get tenants using a specific model as embedding"""
        result = await self.session.execute(
            select(Tenants).where(Tenants.embedding_model_alias == alias)
        )
        return result.scalars().all()
    
    async def get_models_by_status(self, status: str) -> List[ModelRegistry]:
        """Get models by status"""
        result = await self.session.execute(
            select(ModelRegistry).where(ModelRegistry.status == status)
        )
        return result.scalars().all()
    
    async def get_global_models(self) -> List[ModelRegistry]:
        """Get models marked as default/global"""
        result = await self.session.execute(
            select(ModelRegistry).where(ModelRegistry.default_for_type == True)
        )
        return result.scalars().all()

    async def get_global_by_type(self, model_type: ModelType) -> Optional[ModelRegistry]:
        """Get the default model for a given type"""
        result = await self.session.execute(
            select(ModelRegistry).where(
                (ModelRegistry.default_for_type == True) & (ModelRegistry.type == model_type)
            )
        )
        return result.scalars().first()
    
    # Alias for backward compatibility
    async def get_global_by_modality(self, modality: str) -> Optional[ModelRegistry]:
        # Map old modality string to new ModelType
        type_map = {
            "text": ModelType.EMBEDDING,
            "rerank": ModelType.RERANKER,
            "llm": ModelType.LLM_CHAT
        }
        model_type = type_map.get(modality)
        if not model_type:
            return None
        return await self.get_global_by_type(model_type)
    
    async def count_total(self) -> int:
        """Get total count of models"""
        result = await self.session.execute(
            select(func.count(ModelRegistry.id))
        )
        return result.scalar() or 0
