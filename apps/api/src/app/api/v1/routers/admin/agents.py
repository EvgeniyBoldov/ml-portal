"""
Admin agents router v2 - container + version CRUD.

Endpoints:
- GET/POST /agents                                    - list/create containers
- GET/PUT/DELETE /agents/{agent_id}                   - container CRUD by UUID
- GET/POST /agents/{agent_id}/versions                - list/create versions
- GET/PATCH/DELETE /agents/{agent_id}/versions/{version_number} - version CRUD
- POST /agents/{agent_id}/versions/{version_number}/publish
- POST /agents/{agent_id}/versions/{version_number}/archive

All entity operations use UUID, not slug.
"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.services.agent_service import AgentService
from app.schemas.agents import (
    AgentCreate,
    AgentUpdate,
    AgentResponse,
    AgentListItem,
    AgentDetailResponse,
    AgentVersionCreate,
    AgentVersionUpdate,
    AgentVersionResponse,
)
from pydantic import BaseModel, Field

router = APIRouter(tags=["agents"])


class AgentRouteRequest(BaseModel):
    request_text: str = Field(..., min_length=1)


class AgentRouteResponse(BaseModel):
    selected_agent: AgentResponse


# ─────────────────────────────────────────────────────────────────────────────
# AGENT CONTAINER
# ─────────────────────────────────────────────────────────────────────────────

@router.get("", response_model=List[AgentListItem])
async def list_agents(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """List all agents (short schema with versions_count)."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload
    from app.models.agent import Agent

    stmt = (
        select(Agent)
        .options(selectinload(Agent.versions))
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    agents = result.scalars().all()

    return [
        AgentListItem(
            id=a.id,
            slug=a.slug,
            name=a.name,
            description=a.description,
            tags=a.tags,
            current_version_id=a.current_version_id,
            logging_level=a.logging_level,
            allowed_collection_ids=a.allowed_collection_ids,
            versions_count=len(a.versions),
            created_at=a.created_at,
            updated_at=a.updated_at,
        )
        for a in agents
    ]


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    data: AgentCreate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    service = AgentService(db)
    result = await service.create_agent(
        slug=data.slug,
        name=data.name,
        description=data.description,
        tags=data.tags,
        logging_level=data.logging_level,
        model=data.model,
        allowed_collection_ids=data.allowed_collection_ids,
    )
    await db.commit()
    return result


@router.get("/{agent_id}", response_model=AgentDetailResponse)
async def get_agent(
    agent_id: UUID,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    service = AgentService(db)
    return await service.get_agent_detail(agent_id)


@router.post("/router/route", response_model=AgentRouteResponse)
async def route_agent(
    data: AgentRouteRequest,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    service = AgentService(db)
    selected = await service.route_agent(
        request_text=data.request_text,
    )
    if not selected:
        raise HTTPException(status_code=404, detail="No routable agent matches request")
    return AgentRouteResponse(selected_agent=selected)


@router.put("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: UUID,
    data: AgentUpdate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    service = AgentService(db)
    result = await service.update_agent(
        agent_id=agent_id,
        name=data.name,
        description=data.description,
        tags=data.tags,
        logging_level=data.logging_level,
        model=data.model,
        temperature=data.temperature,
        max_tokens=data.max_tokens,
        requires_confirmation_for_write=data.requires_confirmation_for_write,
        risk_level=data.risk_level,
        max_steps=data.max_steps,
        timeout_s=data.timeout_s,
        max_retries=data.max_retries,
        allowed_collection_ids=data.allowed_collection_ids,
    )
    await db.commit()
    return result


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: UUID,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    service = AgentService(db)
    await service.delete_agent(agent_id)
    await db.commit()


# ─────────────────────────────────────────────────────────────────────────────
# AGENT VERSIONS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{agent_id}/versions", response_model=List[AgentVersionResponse])
async def list_versions(
    agent_id: UUID,
    status_filter: Optional[str] = None,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    service = AgentService(db)
    return await service.list_versions_by_agent_id(agent_id, status_filter)


@router.post("/{agent_id}/versions", response_model=AgentVersionResponse, status_code=status.HTTP_201_CREATED)
async def create_version(
    agent_id: UUID,
    data: AgentVersionCreate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    service = AgentService(db)
    result = await service.create_version_by_agent_id(
        agent_id=agent_id,
        data=data.model_dump(exclude_unset=True, exclude={"parent_version_id"}),
        parent_version_id=data.parent_version_id,
    )
    await db.commit()
    return result


@router.get("/{agent_id}/versions/{version_number}", response_model=AgentVersionResponse)
async def get_version(
    agent_id: UUID,
    version_number: int,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    service = AgentService(db)
    return await service.get_version_by_number_and_agent_id(agent_id, version_number)


@router.patch("/{agent_id}/versions/{version_number}", response_model=AgentVersionResponse)
async def update_version(
    agent_id: UUID,
    version_number: int,
    data: AgentVersionUpdate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    service = AgentService(db)
    version = await service.get_version_by_number_and_agent_id(agent_id, version_number)
    result = await service.update_version(
        version_id=version.id,
        data=data.model_dump(exclude_unset=True),
    )
    await db.commit()
    return result


@router.delete("/{agent_id}/versions/{version_number}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_version(
    agent_id: UUID,
    version_number: int,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    service = AgentService(db)
    version = await service.get_version_by_number_and_agent_id(agent_id, version_number)
    await service.delete_version(version.id)
    await db.commit()


@router.post("/{agent_id}/versions/{version_number}/publish", response_model=AgentVersionResponse)
async def publish_version(
    agent_id: UUID,
    version_number: int,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    service = AgentService(db)
    version = await service.get_version_by_number_and_agent_id(agent_id, version_number)
    result = await service.publish_version(version.id)
    await db.commit()
    return result


@router.post("/{agent_id}/versions/{version_number}/archive", response_model=AgentVersionResponse)
async def archive_version(
    agent_id: UUID,
    version_number: int,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Archive an agent version"""
    service = AgentService(db)
    version = await service.get_version_by_number_and_agent_id(agent_id, version_number)
    result = await service.archive_version(version.id)
    await db.commit()
    return result


@router.put("/{agent_id}/current-version", response_model=AgentDetailResponse)
async def set_current_version(
    agent_id: UUID,
    version_id: UUID = Query(..., description="Version ID to set as current"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Set the current version for an agent. Version must be published. Admin only."""
    service = AgentService(db)
    result = await service.set_current_version(agent_id, version_id)
    await db.commit()
    return result
