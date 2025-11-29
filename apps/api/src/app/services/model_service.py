"""Model Service

New architecture: models are added manually via API, not scanned from filesystem.
Service handles CRUD operations and health checks for LLM and Embedding models.
"""
from __future__ import annotations
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update as sa_update, delete as sa_delete
from app.models.model_registry import Model, ModelType, ModelStatus, HealthStatus
from app.core.logging import get_logger

logger = get_logger(__name__)


class ModelService:
    """Service for model CRUD operations and health checks"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create_model(self, data: Dict[str, Any]) -> Model:
        """Create a new model
        
        Args:
            data: Model data (alias, name, type, provider, etc.)
            
        Returns:
            Created model
        """
        # Check if alias already exists
        existing = await self.get_by_alias(data.get("alias"))
        if existing:
            raise ValueError(f"Model with alias '{data['alias']}' already exists")
        
        # If default_for_type=True, unset previous default
        if data.get("default_for_type"):
            await self._unset_default_for_type(data["type"])
        
        model = Model(**data)
        self.session.add(model)
        await self.session.flush()
        
        logger.info(f"Created model: {model.alias} (type={model.type}, provider={model.provider})")
        return model
    
    async def get_by_id(self, model_id: uuid.UUID) -> Optional[Model]:
        """Get model by ID"""
        result = await self.session.execute(
            select(Model).where(
                Model.id == model_id,
                Model.deleted_at.is_(None)
            )
        )
        return result.scalar_one_or_none()
    
    async def get_by_alias(self, alias: str) -> Optional[Model]:
        """Get model by alias"""
        result = await self.session.execute(
            select(Model).where(
                Model.alias == alias,
                Model.deleted_at.is_(None)
            )
        )
        return result.scalar_one_or_none()
    
    async def list_models(
        self,
        type: Optional[ModelType] = None,
        status: Optional[ModelStatus] = None,
        enabled_only: bool = False,
        search: Optional[str] = None
    ) -> List[Model]:
        """List models with filters"""
        query = select(Model).where(Model.deleted_at.is_(None))
        
        if type:
            query = query.where(Model.type == type)
        if status:
            query = query.where(Model.status == status)
        if enabled_only:
            query = query.where(Model.enabled == True)
        if search:
            query = query.where(
                (Model.alias.ilike(f"%{search}%")) |
                (Model.name.ilike(f"%{search}%")) |
                (Model.provider_model_name.ilike(f"%{search}%"))
            )
        
        query = query.order_by(Model.type, Model.alias)
        
        result = await self.session.execute(query)
        return list(result.scalars().all())
    
    async def update_model(
        self,
        model_id: uuid.UUID,
        data: Dict[str, Any]
    ) -> Optional[Model]:
        """Update model
        
        Args:
            model_id: Model ID
            data: Fields to update
            
        Returns:
            Updated model or None if not found
        """
        model = await self.get_by_id(model_id)
        if not model:
            return None
        
        # If setting default_for_type=True, unset previous default
        if data.get("default_for_type") and not model.default_for_type:
            await self._unset_default_for_type(model.type)
        
        # Update fields
        for key, value in data.items():
            if hasattr(model, key):
                setattr(model, key, value)
        
        model.updated_at = datetime.now(timezone.utc)
        await self.session.flush()
        
        logger.info(f"Updated model: {model.alias}")
        return model
    
    async def delete_model(self, model_id: uuid.UUID) -> bool:
        """Soft delete model
        
        Args:
            model_id: Model ID
            
        Returns:
            True if deleted, False if not found
        """
        model = await self.get_by_id(model_id)
        if not model:
            return False
        
        model.deleted_at = datetime.now(timezone.utc)
        model.enabled = False
        await self.session.flush()
        
        logger.info(f"Deleted model: {model.alias}")
        return True
    
    async def get_default_model(self, type: ModelType) -> Optional[Model]:
        """Get default model for type"""
        result = await self.session.execute(
            select(Model).where(
                Model.type == type,
                Model.default_for_type == True,
                Model.enabled == True,
                Model.deleted_at.is_(None)
            ).limit(1)
        )
        return result.scalar_one_or_none()
    
    async def update_health_status(
        self,
        model_id: uuid.UUID,
        status: HealthStatus,
        latency_ms: Optional[int] = None,
        error: Optional[str] = None
    ) -> bool:
        """Update model health status
        
        Args:
            model_id: Model ID
            status: Health status
            latency_ms: Response latency in milliseconds
            error: Error message if unhealthy
            
        Returns:
            True if updated, False if not found
        """
        model = await self.get_by_id(model_id)
        if not model:
            return False
        
        model.health_status = status
        model.health_latency_ms = latency_ms
        model.health_error = error
        model.last_health_check_at = datetime.now(timezone.utc)
        
        # Auto-disable if unhealthy
        if status == HealthStatus.UNAVAILABLE:
            model.status = ModelStatus.UNAVAILABLE
        elif status == HealthStatus.HEALTHY and model.status == ModelStatus.UNAVAILABLE:
            model.status = ModelStatus.AVAILABLE
        
        await self.session.flush()
        
        logger.info(f"Health check for {model.alias}: {status} ({latency_ms}ms)")
        return True
    
    async def _unset_default_for_type(self, type: ModelType):
        """Unset default_for_type for all models of given type"""
        await self.session.execute(
            sa_update(Model)
            .where(Model.type == type, Model.default_for_type == True)
            .values(default_for_type=False)
        )
        await self.session.flush()
