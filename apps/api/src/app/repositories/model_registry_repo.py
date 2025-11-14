"""
Model Registry Repository for database operations
"""
from __future__ import annotations
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func, update
from sqlalchemy.orm import selectinload
from app.models.model_registry import ModelRegistry
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
            if filters.get('state'):
                query = query.where(ModelRegistry.state == filters['state'])
            if filters.get('modality'):
                query = query.where(ModelRegistry.modality == filters['modality'])
            if filters.get('search'):
                search_term = f"%{filters['search']}%"
                query = query.where(
                    or_(
                        ModelRegistry.model.ilike(search_term),
                        ModelRegistry.version.ilike(search_term)
                    )
                )
        
        query = query.order_by(ModelRegistry.model).offset(offset).limit(limit)
        
        result = await self.session.execute(query)
        return result.scalars().all()
    
    async def get_by_id(self, model_id: uuid.UUID) -> Optional[ModelRegistry]:
        """Get model by ID"""
        result = await self.session.execute(
            select(ModelRegistry).where(ModelRegistry.id == model_id)
        )
        return result.scalar_one_or_none()
    
    async def get_by_model(self, model: str) -> Optional[ModelRegistry]:
        """Get model by model identifier"""
        result = await self.session.execute(
            select(ModelRegistry).where(ModelRegistry.model == model)
        )
        return result.scalar_one_or_none()
    
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
    
    async def count_tenants_using(self, model: str) -> int:
        """Count tenants using a specific model"""
        # Count tenants using this model as embed_model
        embed_count = await self.session.execute(
            select(func.count(Tenants.id))
            .where(Tenants.embed_models.contains([model]))
        )
        embed_result = embed_count.scalar() or 0
        
        # Count tenants using this model as rerank_model
        rerank_count = await self.session.execute(
            select(func.count(Tenants.id))
            .where(Tenants.rerank_model == model)
        )
        rerank_result = rerank_count.scalar() or 0
        
        return embed_result + rerank_result
    
    async def get_tenants_by_model(self, model: str) -> List[Tenants]:
        """Get tenants using a specific model"""
        result = await self.session.execute(
            select(Tenants)
            .where(
                or_(
                    Tenants.embed_models.contains([model]),
                    Tenants.rerank_model == model
                )
            )
        )
        return result.scalars().all()
    
    async def get_models_by_state(self, state: str) -> List[ModelRegistry]:
        """Get models by state"""
        result = await self.session.execute(
            select(ModelRegistry).where(ModelRegistry.state == state)
        )
        return result.scalars().all()
    
    async def get_default_models(self) -> List[ModelRegistry]:
        """Get models marked as default for new tenants"""
        result = await self.session.execute(
            select(ModelRegistry).where(ModelRegistry.default_for_new == True)
        )
        return result.scalars().all()
    
    async def count_total(self) -> int:
        """Get total count of models"""
        result = await self.session.execute(
            select(func.count(ModelRegistry.id))
        )
        return result.scalar() or 0
