"""
Agent repositories v2 - container + version pattern.

AgentRepository: CRUD for Agent container.
AgentVersionRepository: CRUD for AgentVersion.

All repos use flush() only. Commit is done in routers/services.
"""
from typing import List, Optional, Tuple
from uuid import UUID
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.agent import Agent
from app.models.agent_version import AgentVersion, AgentVersionStatus


class AgentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, agent: Agent) -> Agent:
        self.session.add(agent)
        await self.session.flush()
        return agent

    async def get_by_id(self, agent_id: UUID) -> Optional[Agent]:
        stmt = select(Agent).where(Agent.id == agent_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_slug(self, slug: str) -> Optional[Agent]:
        stmt = select(Agent).where(Agent.slug == slug)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_slug_with_versions(self, slug: str) -> Optional[Agent]:
        stmt = (
            select(Agent)
            .where(Agent.slug == slug)
            .options(selectinload(Agent.versions))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_with_versions(self, agent_id: UUID) -> Optional[Agent]:
        stmt = (
            select(Agent)
            .where(Agent.id == agent_id)
            .options(selectinload(Agent.versions))
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update(self, agent: Agent, data: dict) -> Agent:
        for key, value in data.items():
            setattr(agent, key, value)
        self.session.add(agent)
        await self.session.flush()
        return agent

    async def delete(self, agent: Agent) -> None:
        await self.session.delete(agent)
        await self.session.flush()

    async def list_agents(
        self,
        skip: int = 0,
        limit: int = 100
    ) -> Tuple[List[Agent], int]:
        count_stmt = select(func.count()).select_from(Agent)
        total = await self.session.scalar(count_stmt) or 0

        stmt = select(Agent).order_by(Agent.slug).offset(skip).limit(limit)
        result = await self.session.execute(stmt)

        return list(result.scalars().all()), total


class AgentVersionRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, version: AgentVersion) -> AgentVersion:
        self.session.add(version)
        await self.session.flush()
        return version

    async def get_by_id(self, version_id: UUID) -> Optional[AgentVersion]:
        stmt = select(AgentVersion).where(AgentVersion.id == version_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_agent_and_version(
        self, agent_id: UUID, version_number: int
    ) -> Optional[AgentVersion]:
        stmt = select(AgentVersion).where(
            AgentVersion.agent_id == agent_id,
            AgentVersion.version == version_number,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_all_by_agent(
        self, agent_id: UUID, status_filter: Optional[str] = None
    ) -> List[AgentVersion]:
        stmt = select(AgentVersion).where(AgentVersion.agent_id == agent_id)
        if status_filter:
            stmt = stmt.where(AgentVersion.status == status_filter)
        stmt = stmt.order_by(AgentVersion.version.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_next_version(self, agent_id: UUID) -> int:
        stmt = select(func.max(AgentVersion.version)).where(
            AgentVersion.agent_id == agent_id
        )
        max_version = await self.session.scalar(stmt)
        return (max_version or 0) + 1

    async def get_published_by_agent(self, agent_id: UUID) -> Optional[AgentVersion]:
        stmt = select(AgentVersion).where(
            AgentVersion.agent_id == agent_id,
            AgentVersion.status == AgentVersionStatus.PUBLISHED.value,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update(self, version: AgentVersion, data: dict) -> AgentVersion:
        for key, value in data.items():
            setattr(version, key, value)
        self.session.add(version)
        await self.session.flush()
        return version

    async def update_status(self, version_id: UUID, status: str) -> None:
        stmt = (
            update(AgentVersion)
            .where(AgentVersion.id == version_id)
            .values(status=status)
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def archive_published_version(self, agent_id: UUID) -> None:
        stmt = (
            update(AgentVersion)
            .where(
                AgentVersion.agent_id == agent_id,
                AgentVersion.status == AgentVersionStatus.PUBLISHED.value,
            )
            .values(status=AgentVersionStatus.ARCHIVED.value)
        )
        await self.session.execute(stmt)
        await self.session.flush()

    async def delete(self, version: AgentVersion) -> None:
        await self.session.delete(version)
        await self.session.flush()
