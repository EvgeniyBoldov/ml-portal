"""Resolve embedding model configuration before constructing an adapter."""
from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.embeddings import EmbeddingServiceFactory, ModelConfig
from app.core.logging import get_logger
from app.models.model_registry import Model, ModelType
from app.services.credential_service import CredentialService

logger = get_logger(__name__)


class EmbeddingModelConfigService:
    """Own database and credential resolution for embedding model adapters."""

    @staticmethod
    async def ensure_registered(session: AsyncSession, model_alias: str) -> None:
        if model_alias in EmbeddingServiceFactory.list_available_models():
            return

        result = await session.execute(
            select(Model).where(
                (Model.alias == model_alias) & (Model.type == ModelType.EMBEDDING)
            )
        )
        model = result.scalars().first()
        if model is None:
            raise RuntimeError(f"Embedding model '{model_alias}' is not configured")

        base_url = model.base_url or ""
        if not base_url and model.instance:
            base_url = model.instance.url or ""
        if not base_url and model.extra_config:
            base_url = model.extra_config.get("base_url", "")

        api_key = await EmbeddingModelConfigService._resolve_api_key(session, model)
        extra_config = model.extra_config or {}
        EmbeddingServiceFactory.register_model(
            ModelConfig(
                alias=model.alias,
                provider=model.provider or "local",
                provider_model_name=model.provider_model_name or model.alias,
                base_url=base_url,
                api_key=api_key,
                dimensions=extra_config.get("vector_dim"),
                extra_config=extra_config,
                connector=getattr(model, "connector", None) or "",
            )
        )

    @staticmethod
    async def _resolve_api_key(session: AsyncSession, model: Model) -> str | None:
        if not model.instance_id:
            return None
        try:
            credentials = await CredentialService(session).resolve_credentials(
                instance_id=model.instance_id,
                strategy="PLATFORM_FIRST",
            )
        except Exception as exc:
            logger.warning(
                "Embedding credential resolution failed for model %s: %s: %s",
                model.alias,
                type(exc).__name__,
                exc,
                exc_info=True,
            )
            return None
        if not credentials:
            return None
        payload: dict[str, Any] = credentials.payload or {}
        if credentials.auth_type in {"api_key", "litellm_api_key"}:
            return payload.get("api_key")
        if credentials.auth_type == "token":
            return payload.get("token")
        return None
