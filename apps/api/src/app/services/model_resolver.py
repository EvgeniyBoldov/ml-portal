"""
ModelResolver — единая точка резолвинга модельных slug'ов.

В БД все модели хранятся по slug (alias): llm.chat.groq.llama4
В LLM-провайдер передаётся provider_model_name: meta-llama/llama-4-maverick-17b-128e-instruct

ModelResolver:
  1. Резолвит slug → provider_model_name (для вызова LLM)
  2. Кэширует маппинг в памяти (TTL-based)
  3. Единственное место в коде, где происходит этот резолвинг
"""
from __future__ import annotations

import time
from typing import Optional, Dict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.model_registry import Model

logger = get_logger(__name__)

# In-memory cache: alias → (provider_model_name, cached_at)
_cache: Dict[str, tuple[str, float]] = {}
_CACHE_TTL_S = 300  # 5 minutes


class ModelResolver:
    """Resolve model slug (alias) → provider_model_name.

    Usage:
        resolver = ModelResolver(session)
        provider_name = await resolver.resolve("llm.chat.groq.llama4")
        # → "meta-llama/llama-4-maverick-17b-128e-instruct"
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def resolve(self, alias: Optional[str]) -> Optional[str]:
        """Resolve slug to provider_model_name.

        Returns provider_model_name if found, otherwise returns alias as-is
        (backward compat for cases when provider_model_name stored directly).
        """
        if not alias:
            return None

        # 1. Check in-memory cache
        cached = _cache.get(alias)
        if cached:
            provider_name, cached_at = cached
            if time.time() - cached_at < _CACHE_TTL_S:
                return provider_name

        # 2. Query DB
        result = await self.session.execute(
            select(Model.provider_model_name).where(
                Model.alias == alias,
                Model.deleted_at.is_(None),
            )
        )
        provider_model_name = result.scalar_one_or_none()

        if provider_model_name:
            _cache[alias] = (provider_model_name, time.time())
            logger.debug(f"Resolved model alias '{alias}' → '{provider_model_name}'")
            return provider_model_name

        # 3. Fallback: alias might already be a provider_model_name (legacy data)
        logger.warning(
            f"Model alias '{alias}' not found in registry, using as-is (legacy fallback)"
        )
        return alias

    async def resolve_or_default(
        self, alias: Optional[str], default_alias: Optional[str] = None
    ) -> Optional[str]:
        """Resolve slug with fallback to default alias."""
        resolved = await self.resolve(alias)
        if resolved and resolved != alias:
            return resolved
        if default_alias:
            return await self.resolve(default_alias)
        return resolved

    @staticmethod
    def invalidate_cache(alias: Optional[str] = None) -> None:
        """Invalidate cache entry or entire cache."""
        if alias:
            _cache.pop(alias, None)
        else:
            _cache.clear()
