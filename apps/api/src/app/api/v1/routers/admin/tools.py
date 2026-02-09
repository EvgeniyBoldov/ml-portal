from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.services.tool_service import ToolService
from app.schemas.tools import ToolCreate, ToolUpdate, ToolResponse

router = APIRouter(tags=["tools"])


@router.get("", response_model=List[ToolResponse])
async def list_tools(
    skip: int = 0,
    limit: int = 100,
    kind: Optional[str] = Query(None, description="Filter by kind: read/write/mixed"),
    tool_group_id: Optional[UUID] = Query(None, description="Filter by tool group"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """List all tools. Admin only."""
    service = ToolService(db)
    tools, _ = await service.list_tools(skip=skip, limit=limit, kind=kind, tool_group_id=tool_group_id)
    return tools


@router.post("", response_model=ToolResponse, status_code=status.HTTP_201_CREATED)
async def create_tool(
    tool: ToolCreate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Create a new tool. Admin only."""
    service = ToolService(db)
    result = await service.create_tool(tool)
    await db.commit()
    return result


@router.get("/{identifier}", response_model=ToolResponse)
async def get_tool(
    identifier: str,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get tool by identifier. Admin only."""
    service = ToolService(db)
    return await service.get_tool(identifier)


@router.put("/{identifier}", response_model=ToolResponse)
async def update_tool(
    identifier: str,
    tool: ToolUpdate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Update tool. Admin only."""
    service = ToolService(db)
    result = await service.update_tool(identifier, tool)
    await db.commit()
    return result


@router.delete("/{identifier}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tool(
    identifier: str,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Delete tool. Admin only."""
    service = ToolService(db)
    await service.delete_tool(identifier)
    await db.commit()
