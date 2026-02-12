"""
Admin agents router v2 - container + version CRUD.

Endpoints:
- GET/POST /agents - list/create containers
- GET/PUT/DELETE /agents/{slug} - container CRUD
- GET/POST /agents/{slug}/versions - list/create versions
- GET/PATCH/DELETE /agents/{slug}/versions/{version} - version CRUD
- POST /agents/{slug}/versions/{version}/activate
- POST /agents/{slug}/versions/{version}/deactivate
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.services.agent_service import (
    AgentService,
    AgentError,
    AgentNotFoundError,
    AgentAlreadyExistsError,
    AgentVersionNotFoundError,
    AgentVersionNotEditableError,
)
from app.schemas.agents import (
    AgentCreate,
    AgentUpdate,
    AgentResponse,
    AgentDetailResponse,
    AgentVersionCreate,
    AgentVersionUpdate,
    AgentVersionResponse,
)

router = APIRouter(tags=["agents"])


# ─────────────────────────────────────────────────────────────────────────────
# AGENT CONTAINER
# ─────────────────────────────────────────────────────────────────────────────

@router.get("", response_model=List[AgentResponse])
async def list_agents(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    service = AgentService(db)
    agents, _ = await service.list_agents(skip=skip, limit=limit)
    return agents


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    data: AgentCreate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    try:
        service = AgentService(db)
        result = await service.create_agent(
            slug=data.slug, name=data.name, description=data.description
        )
        await db.commit()
        return result
    except AgentAlreadyExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.get("/{slug}", response_model=AgentDetailResponse)
async def get_agent(
    slug: str,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    try:
        service = AgentService(db)
        return await service.get_agent_with_versions(slug)
    except AgentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{slug}", response_model=AgentResponse)
async def update_agent(
    slug: str,
    data: AgentUpdate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    try:
        service = AgentService(db)
        agent = await service.get_agent_by_slug(slug)
        result = await service.update_agent(
            agent_id=agent.id, name=data.name, description=data.description
        )
        await db.commit()
        return result
    except AgentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    slug: str,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    try:
        service = AgentService(db)
        agent = await service.get_agent_by_slug(slug)
        await service.delete_agent(agent.id)
        await db.commit()
    except AgentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# AGENT VERSIONS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{slug}/versions", response_model=List[AgentVersionResponse])
async def list_versions(
    slug: str,
    status_filter: Optional[str] = None,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    try:
        service = AgentService(db)
        return await service.list_versions(slug, status_filter)
    except AgentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{slug}/versions", response_model=AgentVersionResponse, status_code=status.HTTP_201_CREATED)
async def create_version(
    slug: str,
    data: AgentVersionCreate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    try:
        service = AgentService(db)
        result = await service.create_version(
            agent_slug=slug,
            prompt=data.prompt,
            policy_id=data.policy_id,
            limit_id=data.limit_id,
            notes=data.notes,
            parent_version_id=data.parent_version_id,
        )
        await db.commit()
        return result
    except AgentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{slug}/versions/{version_number}", response_model=AgentVersionResponse)
async def get_version(
    slug: str,
    version_number: int,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    try:
        service = AgentService(db)
        return await service.get_version_by_number(slug, version_number)
    except (AgentNotFoundError, AgentVersionNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/{slug}/versions/{version_number}", response_model=AgentVersionResponse)
async def update_version(
    slug: str,
    version_number: int,
    data: AgentVersionUpdate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    try:
        service = AgentService(db)
        version = await service.get_version_by_number(slug, version_number)
        result = await service.update_version(
            version_id=version.id,
            prompt=data.prompt,
            policy_id=data.policy_id,
            limit_id=data.limit_id,
            notes=data.notes,
        )
        await db.commit()
        return result
    except (AgentNotFoundError, AgentVersionNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except AgentVersionNotEditableError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{slug}/versions/{version_number}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_version(
    slug: str,
    version_number: int,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    try:
        service = AgentService(db)
        version = await service.get_version_by_number(slug, version_number)
        await service.delete_version(version.id)
        await db.commit()
    except (AgentNotFoundError, AgentVersionNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except AgentError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{slug}/versions/{version_number}/activate", response_model=AgentVersionResponse)
async def activate_version(
    slug: str,
    version_number: int,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    try:
        service = AgentService(db)
        version = await service.get_version_by_number(slug, version_number)
        result = await service.activate_version(version.id)
        await db.commit()
        return result
    except (AgentNotFoundError, AgentVersionNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except AgentError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{slug}/versions/{version_number}/deactivate", response_model=AgentVersionResponse)
async def deactivate_version(
    slug: str,
    version_number: int,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    try:
        service = AgentService(db)
        version = await service.get_version_by_number(slug, version_number)
        result = await service.deactivate_version(version.id)
        await db.commit()
        return result
    except (AgentNotFoundError, AgentVersionNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except AgentError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    slug: str,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Delete agent with cascade delete of all versions and bindings"""
    try:
        service = AgentService(db)
        agent = await service.get_agent_by_slug(slug)
        await service.delete_agent(agent.id)
        await db.commit()
    except AgentNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except AgentError as e:
        raise HTTPException(status_code=400, detail=str(e))
