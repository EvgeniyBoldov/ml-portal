"""
Async Tenants service for tenant management business logic
"""
from __future__ import annotations
from typing import List, Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from app.repositories.tenants_repo import AsyncTenantsRepository
from app.repositories.model_registry_repo import AsyncModelRegistryRepository
from app.models.model_registry import ModelType, ModelStatus
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
        
        # Map extra_embed_model to embedding_model_alias for backward compatibility
        if "extra_embed_model" in tenant_data:
            tenant_data["embedding_model_alias"] = tenant_data.pop("extra_embed_model")
            
        # Validate models if provided
        if "embedding_model_alias" in tenant_data:
            await self.validate_tenant_models(tenant_data.get("embedding_model_alias"))
        
        tenant = await self.repo.create(**tenant_data)
        return await self._build_tenant_response(tenant)
    
    async def update_tenant(self, tenant_id: str, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Update tenant"""
        # Map extra_embed_model to embedding_model_alias for backward compatibility
        if "extra_embed_model" in update_data:
            update_data["embedding_model_alias"] = update_data.pop("extra_embed_model")
            
        # Validate models if provided
        if "embedding_model_alias" in update_data:
            await self.validate_tenant_models(update_data.get("embedding_model_alias"))
        
        tenant = await self.repo.update(uuid.UUID(tenant_id), **update_data)
        if not tenant:
            return None

        return await self._build_tenant_response(tenant)
    
    async def delete_tenant(self, tenant_id: str) -> bool:
        """Delete tenant"""
        return await self.repo.delete(uuid.UUID(tenant_id))
    
    async def validate_tenant_models(self, embedding_model_alias: Optional[str]) -> None:
        """Validate tenant's extra embedding model"""
        if not embedding_model_alias:
            return
        model = await self.model_repo.get_by_alias(embedding_model_alias)
        if not model:
            raise ValueError(f"Embedding model '{embedding_model_alias}' not found")
        if model.type != ModelType.EMBEDDING:
            raise ValueError(f"Model '{embedding_model_alias}' is not an embedding model")
        if model.status != ModelStatus.AVAILABLE:
            raise ValueError(f"Model '{embedding_model_alias}' is not available (status: {model.status})")
        if model.default_for_type:
            raise ValueError("Default embedding model is already in use and cannot be selected as extra")
    
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
            global_embed = await self.model_repo.get_global_by_type(ModelType.EMBEDDING)
        if global_rerank is None:
            global_rerank = await self.model_repo.get_global_by_type(ModelType.RERANKER)

        embed_models: List[str] = []
        embed_models_info: List[Dict[str, Any]] = []

        if global_embed and global_embed.status == ModelStatus.AVAILABLE:
            embed_models.append(global_embed.alias)
            vector_dim = global_embed.extra_config.get('vector_dim') if global_embed.extra_config else None
            embed_models_info.append(
                {
                    "model": global_embed.alias,
                    "version": global_embed.model_version,
                    "vector_dim": vector_dim,
                    "global": True,
                }
            )

        if tenant.embedding_model_alias:
            extra_model = await self.model_repo.get_by_alias(tenant.embedding_model_alias)
            if (
                extra_model
                and extra_model.status == ModelStatus.AVAILABLE
                and extra_model.alias not in embed_models
            ):
                embed_models.append(extra_model.alias)
                vector_dim = extra_model.extra_config.get('vector_dim') if extra_model.extra_config else None
                embed_models_info.append(
                    {
                        "model": extra_model.alias,
                        "version": extra_model.model_version,
                        "vector_dim": vector_dim,
                        "global": False,
                    }
                )

        rerank_model = None
        rerank_model_info = None
        if global_rerank and global_rerank.status == ModelStatus.AVAILABLE:
            rerank_model = global_rerank.alias
            rerank_model_info = {
                "model": global_rerank.alias,
                "version": global_rerank.model_version,
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
            "extra_embed_model": tenant.embedding_model_alias,
            "ocr": tenant.ocr,
            "layout": tenant.layout,
            "default_agent_slug": tenant.default_agent_slug,
            "created_at": tenant.created_at,
            "updated_at": tenant.updated_at,
        }
