"""
Async Tenants service for tenant management business logic
"""
from __future__ import annotations
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.tenants_repo import AsyncTenantsRepository
from app.repositories.model_registry_repo import AsyncModelRegistryRepository
from app.core.logging import get_logger
import uuid

logger = get_logger(__name__)


class AsyncTenantsService:
    """Async service for tenant operations"""
    
    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = AsyncTenantsRepository(session)
        self.model_repo = AsyncModelRegistryRepository(session)
    
    async def get_tenant(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Get tenant by ID"""
        tenant = await self.repo.get_by_id(uuid.UUID(tenant_id))
        if not tenant:
            return None
        
        return self._format_tenant_response(tenant)
    
    async def list_tenants(self, limit: int = 100) -> List[Dict[str, Any]]:
        """List all tenants"""
        tenants = await self.repo.list(limit=limit)
        return [self._format_tenant_response(tenant) for tenant in tenants]
    
    async def create_tenant(self, tenant_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create new tenant"""
        # Validate required fields
        if not tenant_data.get("name"):
            raise ValueError("Tenant name is required")
        
        # Validate models if provided
        if tenant_data.get("embed_models") or tenant_data.get("rerank_model"):
            await self.validate_tenant_models(
                tenant_data.get("embed_models"),
                tenant_data.get("rerank_model")
            )
        
        tenant = await self.repo.create(**tenant_data)
        return self._format_tenant_response(tenant)
    
    async def update_tenant(self, tenant_id: str, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update tenant"""
        # Validate models if provided
        if update_data.get("embed_models") is not None or update_data.get("rerank_model") is not None:
            await self.validate_tenant_models(
                update_data.get("embed_models"),
                update_data.get("rerank_model")
            )
        
        tenant = await self.repo.update(uuid.UUID(tenant_id), **update_data)
        if not tenant:
            return None
        
        return self._format_tenant_response(tenant)
    
    async def delete_tenant(self, tenant_id: str) -> bool:
        """Delete tenant"""
        return await self.repo.delete(uuid.UUID(tenant_id))
    
    async def validate_tenant_models(self, embed_models: Optional[List[str]], rerank_model: Optional[str]) -> None:
        """Validate tenant model selections"""
        if embed_models:
            if len(embed_models) > 2:
                raise ValueError("Maximum 2 embedding models allowed")
            
            # Validate each embed model
            for model_id in embed_models:
                model = await self.model_repo.get_by_model(model_id)
                if not model:
                    raise ValueError(f"Embedding model '{model_id}' not found")
                if model.modality != "text":
                    raise ValueError(f"Model '{model_id}' is not a text embedding model")
                if model.state not in ["active", "archived"]:
                    raise ValueError(f"Model '{model_id}' is not available (state: {model.state})")
        
        if rerank_model:
            model = await self.model_repo.get_by_model(rerank_model)
            if not model:
                raise ValueError(f"Rerank model '{rerank_model}' not found")
            if model.modality != "rerank":
                raise ValueError(f"Model '{rerank_model}' is not a rerank model")
            if model.state not in ["active", "archived"]:
                raise ValueError(f"Model '{rerank_model}' is not available (state: {model.state})")
        
        # Check if at least one active embed model is selected
        if embed_models:
            active_embed_count = 0
            for model_id in embed_models:
                model = await self.model_repo.get_by_model(model_id)
                if model and model.state == "active":
                    active_embed_count += 1
            
            if active_embed_count == 0:
                raise ValueError("At least one active embedding model is required")
    
    async def get_tenant_active_models(self, tenant_id: str) -> Dict[str, Any]:
        """Get active models for a tenant"""
        tenant = await self.repo.get_by_id(uuid.UUID(tenant_id))
        if not tenant:
            raise ValueError("Tenant not found")
        
        active_embed_models = []
        if tenant.embed_models:
            for model_id in tenant.embed_models:
                model = await self.model_repo.get_by_model(model_id)
                if model and model.state == "active":
                    active_embed_models.append({
                        "model": model.model,
                        "version": model.version,
                        "vector_dim": model.vector_dim
                    })
        
        active_rerank_model = None
        if tenant.rerank_model:
            model = await self.model_repo.get_by_model(tenant.rerank_model)
            if model and model.state == "active":
                active_rerank_model = {
                    "model": model.model,
                    "version": model.version
                }
        
        return {
            "embed_models": active_embed_models,
            "rerank_model": active_rerank_model,
            "ocr": tenant.ocr,
            "layout": tenant.layout
        }
    
    def _format_tenant_response(self, tenant) -> Dict[str, Any]:
        """Format tenant model for API response"""
        return {
            "id": str(tenant.id),
            "name": tenant.name,
            "is_active": tenant.is_active,
            "embed_models": tenant.embed_models or [],
            "rerank_model": tenant.rerank_model,
            "ocr": tenant.ocr,
            "layout": tenant.layout,
            "created_at": tenant.created_at,
            "updated_at": tenant.updated_at
        }
