"""
PlatformSettings Repository — data access for the singleton platform settings.
"""
from __future__ import annotations
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform_settings import PlatformSettings
from app.core.logging import get_logger

logger = get_logger(__name__)


class PlatformSettingsRepository:
    """Repository for PlatformSettings (singleton)."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get(self) -> Optional[PlatformSettings]:
        """Get the singleton platform settings row."""
        stmt = select(PlatformSettings).limit(1)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_or_create(self) -> PlatformSettings:
        """Get existing or create new platform settings."""
        settings = await self.get()
        if settings:
            return settings

        settings = PlatformSettings()
        self.session.add(settings)
        await self.session.flush()
        await self.session.refresh(settings)
        logger.info("Created platform settings singleton")
        return settings

    async def update(self, settings: PlatformSettings) -> PlatformSettings:
        await self.session.flush()
        await self.session.refresh(settings)
        return settings
