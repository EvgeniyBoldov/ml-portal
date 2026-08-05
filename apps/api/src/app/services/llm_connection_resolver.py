"""Registry and credential resolution for outbound LLM connections."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import or_, select

from app.adapters.interfaces.llm import ResolvedLLMConnection
from app.core.logging import get_logger
from app.models.model_registry import Model, ModelType
from app.services.credential_service import CredentialService

logger = get_logger(__name__)


class RegistryLLMConnectionResolver:
    """Resolve a model selector once into a provider-safe connection snapshot."""

    @staticmethod
    def _extract_secret(payload: dict, auth_type: str) -> Optional[str]:
        if auth_type in {"api_key", "litellm_api_key"}:
            return payload.get("api_key")
        if auth_type == "token":
            return payload.get("token")
        if auth_type == "basic":
            return payload.get("password")
        return None

    async def resolve(self, model_selector: Optional[str]) -> ResolvedLLMConnection:
        from app.core.db import get_session_factory

        selector = model_selector.strip() if isinstance(model_selector, str) else None
        async with get_session_factory()() as session:
            stmt = (
                select(Model)
                .where(Model.type == ModelType.LLM_CHAT, Model.deleted_at.is_(None), Model.enabled == True)  # noqa: E712
                .order_by(Model.default_for_type.desc(), Model.updated_at.desc())
                .limit(1)
            )
            if selector:
                stmt = (
                    select(Model)
                    .where(
                        Model.type == ModelType.LLM_CHAT,
                        Model.deleted_at.is_(None),
                        Model.enabled == True,  # noqa: E712
                        or_(Model.alias == selector, Model.provider_model_name == selector),
                    )
                    .order_by(Model.default_for_type.desc(), Model.updated_at.desc())
                    .limit(1)
                )
            model = (await session.execute(stmt)).scalar_one_or_none()
            if model is None:
                raise ValueError("LLM model is not configured in registry")
            base_url = model.base_url or (model.instance.url if model.instance else None) or ((model.extra_config or {}).get("base_url"))
            if not base_url:
                raise ValueError("LLM model has no connector/base_url configured")
            api_key: Optional[str] = None
            if model.instance_id:
                decrypted = await CredentialService(session).resolve_credentials(
                    instance_id=model.instance_id, strategy="PLATFORM_FIRST",
                )
                if decrypted:
                    api_key = self._extract_secret(decrypted.payload or {}, decrypted.auth_type)
            return ResolvedLLMConnection(
                model_alias=str(model.alias), provider_model_name=str(model.provider_model_name or model.alias).strip(),
                base_url=str(base_url), connector=getattr(model, "connector", None), api_key=api_key,
                extra_config=dict(model.extra_config or {}),
            )
