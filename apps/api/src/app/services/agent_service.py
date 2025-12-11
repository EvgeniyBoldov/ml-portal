from typing import List, Tuple
from uuid import UUID
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent import Agent
from app.repositories.agent_repository import AgentRepository
from app.schemas.agents import AgentCreate, AgentUpdate


class AgentService:
    def __init__(self, session: AsyncSession):
        self.repo = AgentRepository(session)

    async def list_agents(
        self, 
        skip: int = 0, 
        limit: int = 100
    ) -> Tuple[List[Agent], int]:
        return await self.repo.list_agents(skip, limit)

    async def get_agent(self, identifier: str) -> Agent:
        """Get agent by ID or slug"""
        agent = None
        try:
            # Try as UUID
            uuid_obj = UUID(identifier)
            agent = await self.repo.get_by_id(uuid_obj)
        except ValueError:
            pass
            
        if not agent:
            # Try as slug
            agent = await self.repo.get_by_slug(identifier)
            
        if not agent:
            raise HTTPException(status_code=404, detail=f"Agent '{identifier}' not found")
            
        return agent

    async def create_agent(self, data: AgentCreate) -> Agent:
        # Check slug uniqueness
        existing = await self.repo.get_by_slug(data.slug)
        if existing:
            raise HTTPException(status_code=400, detail=f"Agent with slug '{data.slug}' already exists")
            
        agent = Agent(**data.model_dump())
        return await self.repo.create(agent)

    async def update_agent(self, identifier: str, data: AgentUpdate) -> Agent:
        agent = await self.get_agent(identifier)
        
        update_data = data.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(agent, key, value)
            
        return await self.repo.update(agent)

    async def delete_agent(self, identifier: str) -> None:
        agent = await self.get_agent(identifier)
        await self.repo.delete(agent)
