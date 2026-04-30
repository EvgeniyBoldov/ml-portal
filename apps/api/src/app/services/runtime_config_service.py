"""Runtime config service.

Centralizes runtime config assembly for pipeline using PlatformSettings only.
"""
from __future__ import annotations

from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.services.platform_settings_service import PlatformSettingsProvider

logger = get_logger(__name__)


class RuntimeConfigService:
    """Build effective runtime config used by RuntimePipeline."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_pipeline_config(self) -> Dict[str, Any]:
        """Load pipeline config with safe fallback for partial/test envs."""
        try:
            config = await PlatformSettingsProvider.get_instance().get_config(self.session)
            return dict(config or {})
        except Exception as e:
            error_text = str(e)
            if isinstance(e, AttributeError) and "coroutine" in error_text:
                logger.warning("[RuntimeConfig] Failed to load config, using defaults: %s", e)
                return {}
            logger.error("[RuntimeConfig] Failed to load runtime config", exc_info=True)
            raise RuntimeError("Failed to load runtime config") from e
