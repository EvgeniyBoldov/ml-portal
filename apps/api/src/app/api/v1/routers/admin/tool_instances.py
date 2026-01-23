"""
Tool Instances Admin API
"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.services.tool_instance_service import (
    ToolInstanceService,
    ToolInstanceError,
    ToolInstanceNotFoundError,
    ToolNotFoundError,
)
from app.schemas.tool_instances import (
    ToolInstanceCreate,
    ToolInstanceUpdate,
    ToolInstanceResponse,
    HealthCheckResponse,
)

router = APIRouter(tags=["tool-instances"])


@router.get("", response_model=List[ToolInstanceResponse])
async def list_tool_instances(
    skip: int = 0,
    limit: int = 100,
    tool_slug: Optional[str] = Query(None, description="Filter by tool slug"),
    scope: Optional[str] = Query(None, description="Filter by scope"),
    tenant_id: Optional[UUID] = Query(None, description="Filter by tenant"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """List all tool instances. Admin only."""
    service = ToolInstanceService(db)
    instances, _ = await service.list_instances(
        skip=skip,
        limit=limit,
        tool_slug=tool_slug,
        scope=scope,
        tenant_id=tenant_id,
        is_active=is_active,
    )
    return instances


@router.post("", response_model=ToolInstanceResponse, status_code=status.HTTP_201_CREATED)
async def create_tool_instance(
    data: ToolInstanceCreate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Create a new tool instance. Admin only."""
    service = ToolInstanceService(db)
    try:
        instance = await service.create_instance(
            tool_slug=data.tool_slug,
            slug=data.slug,
            name=data.name,
            scope=data.scope,
            connection_config=data.connection_config,
            tenant_id=data.tenant_id,
            user_id=data.user_id,
            description=data.description,
            is_default=data.is_default,
        )
        await db.commit()
        return instance
    except ToolNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ToolInstanceError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{instance_id}", response_model=ToolInstanceResponse)
async def get_tool_instance(
    instance_id: UUID,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get tool instance by ID. Admin only."""
    service = ToolInstanceService(db)
    try:
        return await service.get_instance(instance_id)
    except ToolInstanceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{instance_id}", response_model=ToolInstanceResponse)
async def update_tool_instance(
    instance_id: UUID,
    data: ToolInstanceUpdate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Update tool instance. Admin only."""
    service = ToolInstanceService(db)
    try:
        instance = await service.update_instance(
            instance_id=instance_id,
            name=data.name,
            description=data.description,
            connection_config=data.connection_config,
            is_default=data.is_default,
            is_active=data.is_active,
        )
        await db.commit()
        return instance
    except ToolInstanceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ToolInstanceError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tool_instance(
    instance_id: UUID,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Delete tool instance. Admin only."""
    service = ToolInstanceService(db)
    try:
        await service.delete_instance(instance_id)
        await db.commit()
    except ToolInstanceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{instance_id}/health-check", response_model=HealthCheckResponse)
async def check_tool_instance_health(
    instance_id: UUID,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Perform health check on tool instance. Admin only."""
    service = ToolInstanceService(db)
    try:
        result = await service.check_health(instance_id)
        await db.commit()
        return HealthCheckResponse(
            status=result.status.value,
            message=result.message,
            details=result.details,
        )
    except ToolInstanceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
