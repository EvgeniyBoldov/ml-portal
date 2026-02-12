"""
PlatformSettings Service — business logic for global platform configuration.
"""
from __future__ import annotations
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform_settings import PlatformSettings
from app.repositories.platform_settings_repository import PlatformSettingsRepository
from app.core.logging import get_logger

logger = get_logger(__name__)


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
        default_policy_id: Optional[UUID] = ...,
        default_limit_id: Optional[UUID] = ...,
    ) -> PlatformSettings:
        """
        Update platform settings. Use None to clear a field.
        Use ... (sentinel) to skip updating a field.
        """
        settings = await self.repo.get_or_create()

        if default_policy_id is not ...:
            settings.default_policy_id = default_policy_id
        if default_limit_id is not ...:
            settings.default_limit_id = default_limit_id

        result = await self.repo.update(settings)
        logger.info("Updated platform settings")
        return result
