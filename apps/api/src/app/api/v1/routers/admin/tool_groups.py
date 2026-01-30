"""
Tool Groups Admin API
"""
from typing import List
from uuid import UUID
from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.services.tool_group_service import (
    ToolGroupService,
    ToolGroupError,
    ToolGroupNotFoundError,
)
from app.schemas.tool_groups import (
    ToolGroupCreate,
    ToolGroupUpdate,
    ToolGroupResponse,
)

router = APIRouter(tags=["tool-groups"])


@router.get("", response_model=List[ToolGroupResponse])
async def list_tool_groups(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """List all tool groups. Admin only."""
    service = ToolGroupService(db)
    groups, _ = await service.list_groups(skip=skip, limit=limit)
    return groups


@router.post("", response_model=ToolGroupResponse, status_code=status.HTTP_201_CREATED)
async def create_tool_group(
    data: ToolGroupCreate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Create a new tool group. Admin only."""
    service = ToolGroupService(db)
    try:
        group = await service.create_group(
            slug=data.slug,
            name=data.name,
            description=data.description,
        )
        await db.commit()
        return group
    except ToolGroupError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{group_id}", response_model=ToolGroupResponse)
async def get_tool_group(
    group_id: UUID,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get tool group by ID. Admin only."""
    service = ToolGroupService(db)
    try:
        return await service.get_group(group_id)
    except ToolGroupNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{group_id}", response_model=ToolGroupResponse)
async def update_tool_group(
    group_id: UUID,
    data: ToolGroupUpdate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Update tool group. Admin only."""
    service = ToolGroupService(db)
    try:
        group = await service.update_group(
            group_id=group_id,
            name=data.name,
            description=data.description,
        )
        await db.commit()
        return group
    except ToolGroupNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ToolGroupError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tool_group(
    group_id: UUID,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Delete tool group. Admin only."""
    service = ToolGroupService(db)
    try:
        await service.delete_group(group_id)
        await db.commit()
    except ToolGroupNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
