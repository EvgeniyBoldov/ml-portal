from __future__ import annotations

from typing import List
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.rag import RAGDocument
from app.repositories.factory import AsyncRepositoryFactory

logger = get_logger(__name__)


class RAGTargetModelService:
    """Resolve effective embedding target models for RAG processing."""

    def __init__(self, session: AsyncSession, repo_factory: AsyncRepositoryFactory):
        self.session = session
        self.repo_factory = repo_factory

    async def get_target_models(self, doc_id: UUID) -> List[str]:
        tenant_id = getattr(self.repo_factory, "tenant_id", None)
        tenant_uuid: UUID | None = None
        if tenant_id:
            try:
                tenant_uuid = tenant_id if isinstance(tenant_id, UUID) else UUID(str(tenant_id))
            except Exception:
                tenant_uuid = None

        if tenant_uuid:
            try:
                return await self.get_target_models_for_tenant(tenant_uuid)
            except Exception as exc:
                logger.warning("Failed to resolve target models for tenant %s: %s", tenant_uuid, exc)
                return []

        try:
            result = await self.session.execute(
                select(RAGDocument.tenant_id).where(RAGDocument.id == doc_id)
            )
            tenant_id = result.scalar_one_or_none()
        except Exception as exc:
            logger.warning("Failed to resolve document tenant for %s: %s", doc_id, exc)
            return []

        if not tenant_id:
            return []

        try:
            return await self.get_target_models_for_tenant(tenant_id)
        except Exception as exc:
            logger.warning("Failed to resolve target models for document %s: %s", doc_id, exc)
            return []

    async def get_target_models_for_tenant(self, tenant_id: UUID) -> List[str]:
        """Resolve effective embedding models for a tenant."""
        from app.models.tenant import Tenants
        from app.models.model_registry import ModelRegistry, ModelType, ModelStatus

        result = await self.session.execute(
            select(Tenants).where(Tenants.id == tenant_id)
        )
        tenant = result.scalar_one_or_none()

        if not tenant:
            return []

        models: List[str] = []

        result = await self.session.execute(
            select(ModelRegistry.alias)
            .where(
                (ModelRegistry.type == ModelType.EMBEDDING)
                & (ModelRegistry.default_for_type == True)
                & (ModelRegistry.enabled == True)
                & (ModelRegistry.status == ModelStatus.AVAILABLE)
                & (ModelRegistry.deleted_at.is_(None))
            )
            .order_by(ModelRegistry.created_at.asc())
            .limit(1)
        )
        global_embed_alias = result.scalar_one_or_none()
        if global_embed_alias:
            models.append(global_embed_alias)
        else:
            # Fallback: if no default is marked, use first available embedding model.
            fallback_result = await self.session.execute(
                select(ModelRegistry.alias)
                .where(
                    (ModelRegistry.type == ModelType.EMBEDDING)
                    & (ModelRegistry.enabled == True)
                    & (ModelRegistry.status == ModelStatus.AVAILABLE)
                    & (ModelRegistry.deleted_at.is_(None))
                )
                .order_by(ModelRegistry.created_at.asc())
                .limit(1)
            )
            fallback_alias = fallback_result.scalar_one_or_none()
            if fallback_alias:
                models.append(fallback_alias)

        tenant_alias = (tenant.embedding_model_alias or "").strip()
        if tenant_alias:
            result = await self.session.execute(
                select(ModelRegistry.alias)
                .where(
                    (ModelRegistry.alias == tenant_alias)
                    & (ModelRegistry.type == ModelType.EMBEDDING)
                    & (ModelRegistry.enabled == True)
                    & (ModelRegistry.status == ModelStatus.AVAILABLE)
                    & (ModelRegistry.deleted_at.is_(None))
                )
                .limit(1)
            )
            tenant_embed_alias = result.scalar_one_or_none()
            if tenant_embed_alias and tenant_embed_alias not in models:
                models.append(tenant_embed_alias)

        return models
