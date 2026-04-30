"""RuntimeSandboxResolver — sandbox override helpers and sandbox agent resolution."""
from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING
from uuid import UUID

from app.core.logging import get_logger
from app.services.sandbox_override_resolver import SandboxOverrideResolver

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.agents.execution_preflight import ExecutionRequest

logger = get_logger(__name__)


class RuntimeSandboxResolver:
    def __init__(self, session: Optional["AsyncSession"] = None) -> None:
        self.session = session

    @staticmethod
    def describe_sandbox_overrides(effective_config: Dict[str, Any]) -> Dict[str, Any]:
        resolver = SandboxOverrideResolver(effective_config)
        return resolver.describe()

    @staticmethod
    def sandbox_agent_slug(effective_config: Dict[str, Any]) -> Optional[str]:
        resolver = SandboxOverrideResolver(effective_config)
        # Only explicit sandbox override should pin agent_slug.
        # Base tenant.default_agent_slug must not force every sandbox run
        # to one agent; otherwise planner cannot route by context.
        raw = resolver.agent_slug_override
        if raw is None:
            return None
        value = str(raw).strip()
        return value or None

    @staticmethod
    def sandbox_agent_version_id(effective_config: Dict[str, Any]) -> Optional[UUID]:
        resolver = SandboxOverrideResolver(effective_config)
        raw = resolver.get_agent_version_override()
        if not raw:
            return None
        try:
            return UUID(str(raw))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def sandbox_runtime_overrides(
        effective_config: Dict[str, Any],
        agent_version: Optional[Any] = None,
    ) -> Dict[str, Any]:
        resolver = SandboxOverrideResolver(effective_config)
        return resolver.to_runtime_overrides(agent_version=agent_version)

    async def resolve_sandbox_agent(
        self,
        *,
        agent_slug: Optional[str],
        tenant_id: UUID,
        agent_version_id: Optional[UUID] = None,
    ) -> Any:
        if self.session is None:
            raise RuntimeError("RuntimeSandboxResolver requires a DB session to resolve sandbox agent state")

        from app.agents.agent_resolver import AgentResolver

        resolver = AgentResolver(self.session)
        return await resolver.resolve(
            agent_slug=agent_slug,
            tenant_id=tenant_id,
            agent_version_id=agent_version_id,
        )
