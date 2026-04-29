"""
PlatformConfigLoader — per-turn read-model of platform configuration.

The pipeline needs three pieces of platform state before stages can run:
    * platform_config dict    (from RuntimeConfigService.get_pipeline_config)
    * routable agents         (from AgentService.list_routable_agents)
    * policy limits           (derived from platform_config.policy)

This loader concentrates all three behind one small dataclass so the
pipeline coordinator does not carry service-level imports or I/O concerns.

Both load methods are defensive — upstream failures degrade to safe
empty defaults and are logged, mirroring the prior pipeline behaviour.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger

logger = get_logger(__name__)


MAX_PLANNER_ITERATIONS_DEFAULT = 12
MAX_WALL_TIME_MS_DEFAULT = 120_000


@dataclass(frozen=True)
class PolicyLimits:
    max_steps: int = MAX_PLANNER_ITERATIONS_DEFAULT
    max_wall_time_ms: int = MAX_WALL_TIME_MS_DEFAULT


@dataclass(frozen=True)
class PlatformSnapshot:
    """Read-only snapshot built for a single pipeline turn."""

    config: Dict[str, Any] = field(default_factory=dict)
    routable_agents: List[Dict[str, Any]] = field(default_factory=list)
    policy: PolicyLimits = field(default_factory=PolicyLimits)

    def available_agents_for_planner(
        self, explicit_slug: Optional[str]
    ) -> List[Dict[str, Any]]:
        """Return the agent set the planner is allowed to pick from.

        When an explicit slug is provided (routing pin or triage hint) we
        present ONLY that agent — without looking it up in `routable_agents`
        so that admins can pin non-routable agents explicitly.
        """
        if explicit_slug:
            return [{"slug": explicit_slug, "description": ""}]
        return list(self.routable_agents)


class PlatformConfigLoader:
    """Async loader; instantiate per-turn and call `load()` once."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def load(self) -> PlatformSnapshot:
        config = await self._load_config()
        agents = await self._list_routable_agents()
        policy = self._derive_policy(config)
        return PlatformSnapshot(config=config, routable_agents=agents, policy=policy)

    # ------------------------------------------------------------------ #
    # Internal helpers                                                   #
    # ------------------------------------------------------------------ #

    async def _load_config(self) -> Dict[str, Any]:
        from app.services.runtime_config_service import RuntimeConfigService

        try:
            return await RuntimeConfigService(self._session).get_pipeline_config()
        except Exception as exc:
            logger.warning("Failed to load platform config, using empty: %s", exc)
            return {}

    async def _list_routable_agents(self) -> List[Dict[str, Any]]:
        from app.services.agent_service import AgentService

        try:
            agents = await AgentService(self._session).list_routable_agents()
        except Exception as exc:
            logger.warning("Failed to list routable agents: %s", exc)
            return []
        return [
            {
                "slug": getattr(a, "slug", None),
                "description": getattr(a, "description", "") or "",
            }
            for a in agents
            if getattr(a, "slug", None)
        ]

    @staticmethod
    def _derive_policy(config: Dict[str, Any]) -> PolicyLimits:
        policy = config.get("policy") if isinstance(config, dict) else None
        policy = policy or {}
        try:
            max_steps = int(policy.get("max_steps") or MAX_PLANNER_ITERATIONS_DEFAULT)
        except (TypeError, ValueError):
            max_steps = MAX_PLANNER_ITERATIONS_DEFAULT
        try:
            max_wall_time_ms = int(policy.get("max_wall_time_ms") or MAX_WALL_TIME_MS_DEFAULT)
        except (TypeError, ValueError):
            max_wall_time_ms = MAX_WALL_TIME_MS_DEFAULT
        return PolicyLimits(max_steps=max_steps, max_wall_time_ms=max_wall_time_ms)
