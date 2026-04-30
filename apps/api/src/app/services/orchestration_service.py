"""
OrchestrationSettings service.

Only executor settings are managed here.
Router/Planner models → SystemLLMRole.
Caps/gates → PlatformSettings.
"""
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.orchestration_settings import OrchestrationSettings
from app.models.agent_version import AgentVersion
from app.models.limit import LimitVersion


class OrchestrationSettingsProvider:
    """Singleton provider for cached orchestration settings."""
    _instance: Optional['OrchestrationSettingsProvider'] = None
    _settings_cache: Optional[Dict[str, Any]] = None

    @classmethod
    def get_instance(cls) -> 'OrchestrationSettingsProvider':
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def invalidate_cache(cls) -> None:
        cls._settings_cache = None

    async def _ensure_cache(self, db: AsyncSession) -> Dict[str, Any]:
        if self._settings_cache is not None:
            return self._settings_cache

        result = await db.execute(select(OrchestrationSettings).limit(1))
        settings = result.scalar_one_or_none()
        if not settings:
            settings = OrchestrationSettings()
            db.add(settings)
            await db.flush()

        self._settings_cache = {
            "executor_model": settings.executor_model,
            "executor_temperature": settings.executor_temperature,
            "executor_timeout_s": settings.executor_timeout_s,
            "executor_max_steps": settings.executor_max_steps,
        }
        return self._settings_cache

    async def get_config(self, db: AsyncSession) -> Dict[str, Any]:
        """Get cached orchestration settings as dict."""
        return await self._ensure_cache(db)

    async def get_effective_config(
        self, 
        db: AsyncSession,
        agent_version: Optional[AgentVersion] = None,
        limit: Optional[LimitVersion] = None,
    ) -> Dict[str, Any]:
        """
        Resolve effective executor configuration.
        Priority: AgentVersion > Limit > OrchestrationSettings.
        """
        settings = await self._ensure_cache(db)

        config = {
            "executor_model": settings.get("executor_model"),
            "executor_temperature": settings.get("executor_temperature") if settings.get("executor_temperature") is not None else 0.7,
            "executor_timeout_s": settings.get("executor_timeout_s") if settings.get("executor_timeout_s") is not None else 60,
            "executor_max_steps": settings.get("executor_max_steps") if settings.get("executor_max_steps") is not None else 10,
        }

        # Override with Limit if provided
        if limit:
            if limit.max_steps is not None:
                config["executor_max_steps"] = limit.max_steps

        return config


class OrchestrationService:
    """Service for managing orchestration settings."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self) -> OrchestrationSettings:
        """Get orchestration settings (singleton)."""
        result = await self.db.execute(select(OrchestrationSettings).limit(1))
        settings = result.scalar_one_or_none()

        if not settings:
            settings = OrchestrationSettings()
            self.db.add(settings)
            await self.db.flush()

        return settings

    async def update_executor(self, updates: dict) -> OrchestrationSettings:
        """Update executor settings."""
        settings = await self.get()

        for key, value in updates.items():
            if hasattr(settings, key):
                setattr(settings, key, value)

        await self.db.flush()
        OrchestrationSettingsProvider.invalidate_cache()
        return settings
