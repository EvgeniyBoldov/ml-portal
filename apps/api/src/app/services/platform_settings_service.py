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
    """Singleton provider for cached platform settings (policies + gates)."""
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
            "required_operation_retry_instruction": settings.required_operation_retry_instruction,
            "operations_rules_text": settings.operations_rules_text,
            "intent_messages": settings.intent_messages,
            "runtime": {
                "synth_chunk_size": settings.synth_chunk_size,
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
        required_operation_retry_instruction: Optional[str] = ...,
        operations_rules_text: Optional[str] = ...,
        intent_messages: Optional[Dict[str, str]] = ...,
        synth_chunk_size: Optional[int] = ...,
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
        if required_operation_retry_instruction is not ...:
            settings.required_operation_retry_instruction = required_operation_retry_instruction
        if operations_rules_text is not ...:
            settings.operations_rules_text = operations_rules_text
        if intent_messages is not ...:
            settings.intent_messages = intent_messages
        if synth_chunk_size is not ...:
            settings.synth_chunk_size = synth_chunk_size

        if chat_upload_max_bytes is not ...:
            settings.chat_upload_max_bytes = chat_upload_max_bytes
        if chat_upload_allowed_extensions is not ...:
            settings.chat_upload_allowed_extensions = chat_upload_allowed_extensions

        result = await self.repo.update(settings)
        PlatformSettingsProvider.invalidate_cache()
        logger.info("Updated platform settings")
        return result
