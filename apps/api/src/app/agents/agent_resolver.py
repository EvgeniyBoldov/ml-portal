"""
AgentResolver — загрузка агента, версии и available_actions.

Отвечает ТОЛЬКО за:
- Загрузку Agent по slug
- Резолв active AgentVersion (или override)
- Сборку AvailableActions (whitelist для planner)
"""
from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.available_actions import AvailableActionsBuilder
from app.agents.contracts import AvailableActions, ResolvedOperation
from app.core.logging import get_logger
from app.models.agent import Agent
from app.models.agent_version import AgentVersion
from app.services.agent_service import AgentService

logger = get_logger(__name__)


class AgentResolveResult:
    """Результат резолва агента."""

    __slots__ = ("agent", "agent_version", "available_actions")

    def __init__(
        self,
        agent: Agent,
        agent_version: AgentVersion,
        available_actions: AvailableActions,
    ) -> None:
        self.agent = agent
        self.agent_version = agent_version
        self.available_actions = available_actions


class AgentResolver:
    """Загружает агента, его версию и строит available_actions."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.agent_service = AgentService(session)
        self.available_actions_builder = AvailableActionsBuilder(session)

    async def resolve(
        self,
        agent_slug: Optional[str],
        tenant_id: UUID,
        resolved_operations: Optional[List[ResolvedOperation]] = None,
        agent_version_id: Optional[UUID] = None,
        include_routable_agents: bool = True,
    ) -> AgentResolveResult:
        """Resolve agent, version and available_actions.

        Args:
            agent_slug: Slug агента.
            tenant_id: Tenant UUID.
            resolved_operations: Список доступных operations.
            agent_version_id: Override версии (sandbox).

        Returns:
            AgentResolveResult с agent, agent_version, available_actions.
        """
        if agent_version_id:
            ver_result = await self.session.execute(
                select(AgentVersion).where(AgentVersion.id == agent_version_id)
            )
            agent_version = ver_result.scalar_one_or_none()
            if not agent_version:
                raise ValueError(f"AgentVersion {agent_version_id} not found")
            agent = await self.agent_service.get_agent_with_versions_by_id(agent_version.agent_id)
        elif agent_slug:
            agent = await self.agent_service.get_agent_by_slug(agent_slug)
            agent_version = await self.agent_service.resolve_published_version(
                agent_slug, tenant_id=tenant_id
            )
        else:
            agent_version = await self.agent_service.resolve_published_version(
                None, tenant_id=tenant_id
            )
            agent = await self.agent_service.get_agent_with_versions_by_id(agent_version.agent_id)

        routable_agents = await self.agent_service.list_routable_agents() if include_routable_agents else []
        available_actions = await self.available_actions_builder.build(
            agent=agent,
            agent_version=agent_version,
            resolved_operations=resolved_operations or [],
            routable_agents=routable_agents,
        )

        return AgentResolveResult(
            agent=agent,
            agent_version=agent_version,
            available_actions=available_actions,
        )
