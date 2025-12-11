from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.services.tool_service import ToolService
from app.schemas.tools import ToolCreate, ToolUpdate, ToolResponse

router = APIRouter(tags=["tools"])


@router.get("", response_model=List[ToolResponse])
async def list_tools(
    skip: int = 0,
    limit: int = 100,
    type: Optional[str] = Query(None, description="Filter by type"),
    db: AsyncSession = Depends(get_db),
):
    service = ToolService(db)
    tools, _ = await service.list_tools(skip=skip, limit=limit, type_filter=type)
    return tools


@router.post("", response_model=ToolResponse, status_code=status.HTTP_201_CREATED)
async def create_tool(
    tool: ToolCreate,
    db: AsyncSession = Depends(get_db),
):
    service = ToolService(db)
    return await service.create_tool(tool)


@router.get("/{identifier}", response_model=ToolResponse)
async def get_tool(
    identifier: str,
    db: AsyncSession = Depends(get_db),
):
    service = ToolService(db)
    return await service.get_tool(identifier)


@router.put("/{identifier}", response_model=ToolResponse)
async def update_tool(
    identifier: str,
    tool: ToolUpdate,
    db: AsyncSession = Depends(get_db),
):
    service = ToolService(db)
    return await service.update_tool(identifier, tool)


@router.delete("/{identifier}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tool(
    identifier: str,
    db: AsyncSession = Depends(get_db),
):
    service = ToolService(db)
    await service.delete_tool(identifier)
