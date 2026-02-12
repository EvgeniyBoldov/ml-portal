"""
Tool Instances Admin API v3

Instance types:
- LOCAL: auto-managed (RAG, collections). Cannot be created/deleted via API.
- REMOTE: user-managed (jira, netbox, crm). Full CRUD via API.
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
    LocalInstanceProtectedError,
)
from app.schemas.tool_instances import (
    ToolInstanceCreate,
    ToolInstanceUpdate,
    ToolInstanceResponse,
    HealthCheckResponse,
    RescanResponse,
)

router = APIRouter(tags=["tool-instances"])


@router.get("", response_model=List[ToolInstanceResponse])
async def list_tool_instances(
    skip: int = 0,
    limit: int = 100,
    tool_group_id: Optional[UUID] = Query(None, description="Filter by tool group"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    instance_type: Optional[str] = Query(None, description="Filter: local|remote"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """List all tool instances. Admin only."""
    service = ToolInstanceService(db)
    instances, _ = await service.list_instances(
        skip=skip,
        limit=limit,
        tool_group_id=tool_group_id,
        is_active=is_active,
        instance_type=instance_type,
    )
    return instances


@router.post("", response_model=ToolInstanceResponse, status_code=status.HTTP_201_CREATED)
async def create_tool_instance(
    data: ToolInstanceCreate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Create a new REMOTE tool instance. Local instances are auto-managed."""
    import re
    slug = data.slug
    if not slug:
        slug = re.sub(r'[^a-z0-9]+', '-', data.name.lower()).strip('-')
    
    service = ToolInstanceService(db)
    try:
        instance = await service.create_instance(
            tool_group_id=data.tool_group_id,
            slug=slug,
            name=data.name,
            url=data.url,
            description=data.description,
            config=data.config,
            category=data.category,
        )
        await db.commit()
        return instance
    except ToolInstanceError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/rescan", response_model=RescanResponse)
async def rescan_instances(
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """
    Rescan and sync local instances with actual data.
    Ensures RAG global instance exists and collection instances are in sync.
    """
    service = ToolInstanceService(db)
    result = await service.rescan_local_instances()
    await db.commit()
    return RescanResponse(
        created=result.created,
        updated=result.updated,
        deleted=result.deleted,
        errors=result.errors,
    )


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
    """Update tool instance. Local instances can only toggle is_active."""
    service = ToolInstanceService(db)
    try:
        instance = await service.update_instance(
            instance_id=instance_id,
            name=data.name,
            description=data.description,
            url=data.url,
            config=data.config,
            is_active=data.is_active,
            category=data.category,
        )
        await db.commit()
        return instance
    except ToolInstanceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except LocalInstanceProtectedError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ToolInstanceError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{instance_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tool_instance(
    instance_id: UUID,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Delete REMOTE tool instance. Local instances cannot be deleted."""
    service = ToolInstanceService(db)
    try:
        await service.delete_instance(instance_id)
        await db.commit()
    except ToolInstanceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except LocalInstanceProtectedError as e:
        raise HTTPException(status_code=403, detail=str(e))


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
            status=result.status,
            message=result.message,
            details=result.details,
        )
    except ToolInstanceNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
