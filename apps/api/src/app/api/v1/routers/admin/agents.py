from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.services.agent_service import AgentService
from app.schemas.agents import AgentCreate, AgentUpdate, AgentResponse

router = APIRouter(tags=["agents"])


@router.get("", response_model=List[AgentResponse])
async def list_agents(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    service = AgentService(db)
    agents, _ = await service.list_agents(skip=skip, limit=limit)
    return agents


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    agent: AgentCreate,
    db: AsyncSession = Depends(get_db),
):
    service = AgentService(db)
    return await service.create_agent(agent)


@router.get("/{identifier}", response_model=AgentResponse)
async def get_agent(
    identifier: str,
    db: AsyncSession = Depends(get_db),
):
    service = AgentService(db)
    return await service.get_agent(identifier)


@router.put("/{identifier}", response_model=AgentResponse)
async def update_agent(
    identifier: str,
    agent: AgentUpdate,
    db: AsyncSession = Depends(get_db),
):
    service = AgentService(db)
    return await service.update_agent(identifier, agent)


@router.delete("/{identifier}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    identifier: str,
    db: AsyncSession = Depends(get_db),
):
    service = AgentService(db)
    await service.delete_agent(identifier)
