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
        
        return await self._build_tenant_response(tenant)
    
    async def list_tenants(self, limit: int = 100) -> List[Dict[str, Any]]:
        """List all tenants"""
        tenants = await self.repo.list(limit=limit)
        results: List[Dict[str, Any]] = []
        for t in tenants:
            results.append(await self._build_tenant_response(t))
        return results
    
    async def create_tenant(self, tenant_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Create new tenant"""
        # Validate required fields
        if not tenant_data.get("name"):
            raise ValueError("Tenant name is required")
        
        # Validate models if provided
        if "extra_embed_model" in tenant_data:
            await self.validate_tenant_models(tenant_data.get("extra_embed_model"))
        
        tenant = await self.repo.create(**tenant_data)
        return await self._build_tenant_response(tenant)
    
    async def update_tenant(self, tenant_id: str, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update tenant"""
        # Validate models if provided
        if "extra_embed_model" in update_data:
            await self.validate_tenant_models(update_data.get("extra_embed_model"))
        
        tenant = await self.repo.update(uuid.UUID(tenant_id), **update_data)
        if not tenant:
            return None

        return await self._build_tenant_response(tenant)
    
    async def delete_tenant(self, tenant_id: str) -> bool:
        """Delete tenant"""
        return await self.repo.delete(uuid.UUID(tenant_id))
    
    async def validate_tenant_models(self, extra_embed_model: Optional[str]) -> None:
        """Validate tenant's extra embedding model"""
        if not extra_embed_model:
            return
        model = await self.model_repo.get_by_model(extra_embed_model)
        if not model:
            raise ValueError(f"Embedding model '{extra_embed_model}' not found")
        if model.modality != "text":
            raise ValueError(f"Model '{extra_embed_model}' is not a text embedding model")
        if model.state not in ["active", "archived"]:
            raise ValueError(f"Model '{extra_embed_model}' is not available (state: {model.state})")
        if model.is_global:
            raise ValueError("Global embedding model is already in use and cannot be selected as extra")
    
    async def get_tenant_active_models(self, tenant_id: str) -> Dict[str, Any]:
        """Get resolved active models for a tenant: global embedding + optional extra, and global reranker"""
        tenant = await self.repo.get_by_id(uuid.UUID(tenant_id))
        if not tenant:
            raise ValueError("Tenant not found")
        
        response = await self._build_tenant_response(tenant)
        return {
            "embed_models": response["embed_models_info"],
            "rerank_model": response["rerank_model_info"],
            "ocr": response["ocr"],
            "layout": response["layout"],
        }

    async def _build_tenant_response(
        self,
        tenant,
        global_embed=None,
        global_rerank=None,
    ) -> Dict[str, Any]:
        if global_embed is None:
            global_embed = await self.model_repo.get_global_by_modality("text")
        if global_rerank is None:
            global_rerank = await self.model_repo.get_global_by_modality("rerank")

        embed_models: List[str] = []
        embed_models_info: List[Dict[str, Any]] = []

        if global_embed and global_embed.state == "active":
            embed_models.append(global_embed.model)
            embed_models_info.append(
                {
                    "model": global_embed.model,
                    "version": global_embed.version,
                    "vector_dim": global_embed.vector_dim,
                    "global": True,
                }
            )

        if tenant.extra_embed_model:
            extra_model = await self.model_repo.get_by_model(tenant.extra_embed_model)
            if extra_model and extra_model.state in ["active", "archived"]:
                embed_models.append(extra_model.model)
                embed_models_info.append(
                    {
                        "model": extra_model.model,
                        "version": extra_model.version,
                        "vector_dim": extra_model.vector_dim,
                        "global": False,
                    }
                )

        rerank_model = None
        rerank_model_info = None
        if global_rerank and global_rerank.state == "active":
            rerank_model = global_rerank.model
            rerank_model_info = {
                "model": global_rerank.model,
                "version": global_rerank.version,
                "global": True,
            }

        return {
            "id": str(tenant.id),
            "name": tenant.name,
            "description": tenant.description,
            "is_active": tenant.is_active,
            "embed_models": embed_models,
            "embed_models_info": embed_models_info,
            "rerank_model": rerank_model,
            "rerank_model_info": rerank_model_info,
            "extra_embed_model": tenant.extra_embed_model,
            "ocr": tenant.ocr,
            "layout": tenant.layout,
            "created_at": tenant.created_at,
            "updated_at": tenant.updated_at,
        }
