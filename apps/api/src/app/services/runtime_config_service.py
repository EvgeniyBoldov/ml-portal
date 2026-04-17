"""Runtime config service.

Centralizes runtime config assembly for pipeline:
- Platform settings (base)
- Orchestration fail-policy overrides
"""
from __future__ import annotations

from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.services.orchestration_service import OrchestrationSettingsProvider
from app.services.platform_settings_service import PlatformSettingsProvider

logger = get_logger(__name__)


class RuntimeConfigService:
    """Build effective runtime config used by RuntimePipeline."""

    _ORCHESTRATION_FAIL_POLICY_KEYS = (
        "triage_fail_open",
        "preflight_fail_open",
        "planner_fail_open",
        "preflight_fail_open_message",
        "planner_fail_open_message",
    )

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_pipeline_config(self) -> Dict[str, Any]:
        """Load pipeline config with safe fallback for partial/test envs."""
        try:
            config = await PlatformSettingsProvider.get_instance().get_config(self.session)
            return await self._merge_orchestration_fail_policy(config)
        except Exception as e:
            error_text = str(e)
            if isinstance(e, AttributeError) and "coroutine" in error_text:
                logger.warning("[RuntimeConfig] Failed to load config, using defaults: %s", e)
                return {}
            logger.error("[RuntimeConfig] Failed to load runtime config", exc_info=True)
            raise RuntimeError("Failed to load runtime config") from e

    async def _merge_orchestration_fail_policy(self, base_config: Dict[str, Any]) -> Dict[str, Any]:
        config = dict(base_config or {})
        try:
            orchestration = await OrchestrationSettingsProvider.get_instance().get_config(self.session)
            for key in self._ORCHESTRATION_FAIL_POLICY_KEYS:
                value = orchestration.get(key)
                if value is not None:
                    config[key] = value
        except Exception as e:
            logger.warning(
                "[RuntimeConfig] Failed to merge orchestration fail policy: %s",
                e,
            )
        return config
