"""
PlatformSettings Service — business logic for global platform configuration.
"""
from __future__ import annotations
from typing import Optional, Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.platform_settings import PlatformSettings
from app.repositories.platform_settings_repository import PlatformSettingsRepository
from app.core.logging import get_logger

logger = get_logger(__name__)


class PlatformSettingsProvider:
    """Singleton provider for cached platform settings (gates + caps)."""
    _instance: Optional[PlatformSettingsProvider] = None
    _cache: Optional[Dict[str, Any]] = None

    @classmethod
    def get_instance(cls) -> PlatformSettingsProvider:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def invalidate_cache(cls) -> None:
        cls._cache = None

    async def get_config(self, db: AsyncSession) -> Dict[str, Any]:
        """Get cached platform settings as dict."""
        if self._cache is not None:
            return self._cache

        result = await db.execute(select(PlatformSettings).limit(1))
        settings = result.scalar_one_or_none()
        if not settings:
            settings = PlatformSettings()
            db.add(settings)
            await db.flush()

        self._cache = {
            # Policy gates
            "policies_text": settings.policies_text,
            "require_confirmation_for_write": settings.require_confirmation_for_write or False,
            "require_confirmation_for_destructive": settings.require_confirmation_for_destructive or False,
            "forbid_destructive": settings.forbid_destructive or False,
            "forbid_write_in_prod": settings.forbid_write_in_prod or False,
            "require_backup_before_write": settings.require_backup_before_write or False,
            # Absolute caps
            "abs_max_timeout_s": settings.abs_max_timeout_s,
            "abs_max_retries": settings.abs_max_retries,
            "abs_max_steps": settings.abs_max_steps,
            "abs_max_plan_steps": settings.abs_max_plan_steps,
            "abs_max_concurrency": settings.abs_max_concurrency,
            "abs_max_task_runtime_s": settings.abs_max_task_runtime_s,
            "abs_max_tool_calls_per_step": settings.abs_max_tool_calls_per_step,
            "runtime_budget": {
                "max_planner_iterations": settings.budget_max_planner_iterations or 12,
                "max_agent_steps": settings.budget_max_agent_steps or 20,
                "max_tool_calls_total": settings.budget_max_tool_calls_total or 50,
                "max_wall_time_ms": settings.budget_max_wall_time_ms or 120000,
                "per_tool_timeout_ms": settings.budget_per_tool_timeout_ms or 30000,
                "max_steps_without_success": settings.budget_max_steps_without_success or 2,
                "loop_threshold": settings.budget_loop_threshold or 3,
                "max_retries": settings.budget_max_retries or 3,
                "max_tokens_total": settings.budget_max_tokens_total,
            },
            # Chat upload settings
            "chat_upload_max_bytes": settings.chat_upload_max_bytes,
            "chat_upload_allowed_extensions": settings.chat_upload_allowed_extensions,
        }
        return self._cache


class PlatformSettingsService:
    """Service for platform settings operations."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.repo = PlatformSettingsRepository(session)

    async def get(self) -> PlatformSettings:
        """Get platform settings (creates if not exists)."""
        return await self.repo.get_or_create()

    async def update(
        self,
        # === Global Policy Settings ===
        policies_text: Optional[str] = ...,
        require_confirmation_for_write: Optional[bool] = ...,
        require_confirmation_for_destructive: Optional[bool] = ...,
        forbid_destructive: Optional[bool] = ...,
        forbid_write_in_prod: Optional[bool] = ...,
        require_backup_before_write: Optional[bool] = ...,
        # === Global Caps / Rails ===
        abs_max_timeout_s: Optional[int] = ...,
        abs_max_retries: Optional[int] = ...,
        abs_max_steps: Optional[int] = ...,
        abs_max_plan_steps: Optional[int] = ...,
        abs_max_concurrency: Optional[int] = ...,
        abs_max_task_runtime_s: Optional[int] = ...,
        abs_max_tool_calls_per_step: Optional[int] = ...,
        budget_max_planner_iterations: Optional[int] = ...,
        budget_max_agent_steps: Optional[int] = ...,
        budget_max_tool_calls_total: Optional[int] = ...,
        budget_max_wall_time_ms: Optional[int] = ...,
        budget_per_tool_timeout_ms: Optional[int] = ...,
        budget_max_steps_without_success: Optional[int] = ...,
        budget_loop_threshold: Optional[int] = ...,
        budget_max_retries: Optional[int] = ...,
        budget_max_tokens_total: Optional[int] = ...,
        # === Chat File Upload ===
        chat_upload_max_bytes: Optional[int] = ...,
        chat_upload_allowed_extensions: Optional[str] = ...,
    ) -> PlatformSettings:
        """
        Update platform settings. Use None to clear a field.
        Use ... (sentinel) to skip updating a field.
        """
        settings = await self.repo.get_or_create()

        # === Global Policy Settings ===
        if policies_text is not ...:
            settings.policies_text = policies_text
        if require_confirmation_for_write is not ...:
            settings.require_confirmation_for_write = require_confirmation_for_write
        if require_confirmation_for_destructive is not ...:
            settings.require_confirmation_for_destructive = require_confirmation_for_destructive
        if forbid_destructive is not ...:
            settings.forbid_destructive = forbid_destructive
        if forbid_write_in_prod is not ...:
            settings.forbid_write_in_prod = forbid_write_in_prod
        if require_backup_before_write is not ...:
            settings.require_backup_before_write = require_backup_before_write

        # === Global Caps / Rails ===
        if abs_max_timeout_s is not ...:
            settings.abs_max_timeout_s = abs_max_timeout_s
        if abs_max_retries is not ...:
            settings.abs_max_retries = abs_max_retries
        if abs_max_steps is not ...:
            settings.abs_max_steps = abs_max_steps
        if abs_max_plan_steps is not ...:
            settings.abs_max_plan_steps = abs_max_plan_steps
        if abs_max_concurrency is not ...:
            settings.abs_max_concurrency = abs_max_concurrency
        if abs_max_task_runtime_s is not ...:
            settings.abs_max_task_runtime_s = abs_max_task_runtime_s
        if abs_max_tool_calls_per_step is not ...:
            settings.abs_max_tool_calls_per_step = abs_max_tool_calls_per_step
        if budget_max_planner_iterations is not ...:
            settings.budget_max_planner_iterations = budget_max_planner_iterations
        if budget_max_agent_steps is not ...:
            settings.budget_max_agent_steps = budget_max_agent_steps
        if budget_max_tool_calls_total is not ...:
            settings.budget_max_tool_calls_total = budget_max_tool_calls_total
        if budget_max_wall_time_ms is not ...:
            settings.budget_max_wall_time_ms = budget_max_wall_time_ms
        if budget_per_tool_timeout_ms is not ...:
            settings.budget_per_tool_timeout_ms = budget_per_tool_timeout_ms
        if budget_max_steps_without_success is not ...:
            settings.budget_max_steps_without_success = budget_max_steps_without_success
        if budget_loop_threshold is not ...:
            settings.budget_loop_threshold = budget_loop_threshold
        if budget_max_retries is not ...:
            settings.budget_max_retries = budget_max_retries
        if budget_max_tokens_total is not ...:
            settings.budget_max_tokens_total = budget_max_tokens_total
        if chat_upload_max_bytes is not ...:
            settings.chat_upload_max_bytes = chat_upload_max_bytes
        if chat_upload_allowed_extensions is not ...:
            settings.chat_upload_allowed_extensions = chat_upload_allowed_extensions

        result = await self.repo.update(settings)
        PlatformSettingsProvider.invalidate_cache()
        logger.info("Updated platform settings")
        return result
