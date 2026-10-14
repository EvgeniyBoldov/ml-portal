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
        from app.services.model_capabilities import ModelCapabilities
        capabilities = ModelCapabilities.from_model(model)
        if not capabilities.embedding_dimensions or not capabilities.max_input_tokens:
            from app.services.model_metadata_service import _probe_manifest
            manifest, _ = await _probe_manifest(base_url, connector=getattr(model, "connector", None),
                api_key=api_key, extra_config=extra_config, provider_model_name=model.provider_model_name)
            observed = ModelCapabilities.from_manifest(manifest, embedding=True)
            for field in ("embedding_dimensions", "max_input_tokens", "model_version", "vector_normalized"):
                configured, reported = getattr(capabilities, field), getattr(observed, field)
                if configured is not None and reported is not None and configured != reported:
                    raise ValueError(f"Embedding characteristic {field} differs from the service for {model_alias}; verify the model")
            manifest = {key: value for key, value in manifest.items() if key != "important_params"}
            extra_config = {**extra_config, "manifest": manifest}
            model.extra_config = extra_config
            from datetime import datetime, timezone
            model.capabilities_checked_at = datetime.now(timezone.utc)
            capabilities = ModelCapabilities(
                embedding_dimensions=capabilities.embedding_dimensions or observed.embedding_dimensions,
                max_input_tokens=capabilities.max_input_tokens or observed.max_input_tokens,
                vector_normalized=capabilities.vector_normalized if capabilities.vector_normalized is not None else observed.vector_normalized,
                model_version=capabilities.model_version or observed.model_version,
            )
        if not capabilities.embedding_dimensions or not capabilities.max_input_tokens:
            raise ValueError(f"Embedding capabilities are unknown for '{model_alias}'; verify the model")
        # Persist discovered/legacy capabilities inside the caller's transaction;
        # repositories/services never commit a search or worker transaction here.
        changed = False
        for key, value in capabilities.model_dump().items():
            if value is not None and getattr(model, key, None) is None:
                setattr(model, key, value)
                changed = True
        if changed:
            await session.flush()
        EmbeddingServiceFactory.register_model(
            ModelConfig(
                alias=model.alias,
                provider=model.provider or "local",
                provider_model_name=model.provider_model_name or model.alias,
                base_url=base_url,
                api_key=api_key,
                dimensions=capabilities.embedding_dimensions,
                max_tokens=capabilities.max_input_tokens,
                model_version=capabilities.model_version,
                normalized=capabilities.vector_normalized,
                request_timeout_s=getattr(model, "request_timeout_s", None) or 30.0,
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
