"""Discovered tools admin API."""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.models.discovered_tool import DiscoveredTool
from app.models.tool import Tool
from app.services.tool_discovery_service import ToolDiscoveryService
from app.schemas.discovered_tools import (
    DiscoveredToolsRescanRequest,
    DiscoveredToolListItem,
    DiscoveredToolDetailResponse,
    DiscoveredToolUpdateRequest,
    McpOnboardRequest,
    McpOnboardResponse,
    McpProbeResponse,
    RescanResponse,
)

router = APIRouter(tags=["discovered-tools"])


def _to_list_item(tool: DiscoveredTool) -> DiscoveredToolListItem:
    provider = getattr(tool, "provider_instance", None)
    return DiscoveredToolListItem.model_validate(tool).model_copy(
        update={
            "tool_id": getattr(tool, "tool_id", None),
            "connector_slug": getattr(provider, "slug", None),
            "connector_name": getattr(provider, "name", None),
        }
    )


def _to_detail_item(tool: DiscoveredTool) -> DiscoveredToolDetailResponse:
    provider = getattr(tool, "provider_instance", None)
    return DiscoveredToolDetailResponse.model_validate(tool).model_copy(
        update={
            "tool_id": getattr(tool, "tool_id", None),
            "connector_slug": getattr(provider, "slug", None),
            "connector_name": getattr(provider, "name", None),
        }
    )


@router.get("", response_model=List[DiscoveredToolListItem])
async def list_discovered_tools(
    source: Optional[str] = Query(None, description="Filter by source: local | mcp"),
    provider_instance_id: Optional[UUID] = Query(None, description="Filter by provider instance id"),
    domain: Optional[str] = Query(None, description="Filter by domain"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """List all discovered tools with optional filters."""
    service = ToolDiscoveryService(db)
    tools = await service.list_all(
        source=source,
        provider_instance_id=provider_instance_id,
        domain=domain,
        is_active=is_active,
    )
    return [_to_list_item(t) for t in tools]


@router.get("/{tool_id}", response_model=DiscoveredToolDetailResponse)
async def get_discovered_tool(
    tool_id: UUID,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get discovered tool detail by UUID."""
    stmt = (
        select(DiscoveredTool)
        .options(selectinload(DiscoveredTool.tool), selectinload(DiscoveredTool.provider_instance))
        .where(DiscoveredTool.id == tool_id)
    )
    result = await db.execute(stmt)
    tool = result.scalar_one_or_none()
    if not tool:
        raise HTTPException(status_code=404, detail=f"Discovered tool '{tool_id}' not found")
    return _to_detail_item(tool)


@router.patch("/{tool_id}", response_model=DiscoveredToolDetailResponse)
async def update_discovered_tool(
    tool_id: UUID,
    data: DiscoveredToolUpdateRequest,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Link or unlink discovered capability with a tool publication container."""
    stmt = (
        select(DiscoveredTool)
        .options(selectinload(DiscoveredTool.tool))
        .where(DiscoveredTool.id == tool_id)
    )
    result = await db.execute(stmt)
    tool = result.scalar_one_or_none()
    if not tool:
        raise HTTPException(status_code=404, detail=f"Discovered tool '{tool_id}' not found")

    if "tool_id" in data.model_fields_set:
        if data.tool_id is not None:
            linked_tool = await db.get(Tool, data.tool_id)
            if not linked_tool:
                raise HTTPException(status_code=404, detail=f"Tool '{data.tool_id}' not found")
            tool.tool_id = linked_tool.id
        else:
            tool.tool_id = None

    await db.flush()
    await db.refresh(tool)
    await db.commit()
    await db.refresh(tool, attribute_names=["tool"])
    return _to_detail_item(tool)


@router.post("/probe-mcp", response_model=McpProbeResponse)
async def probe_mcp_provider(
    provider_instance_id: UUID = Query(..., description="MCP service instance id"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Probe MCP provider and return discovered tool descriptors without persistence."""
    service = ToolDiscoveryService(db)
    try:
        result = await service.probe_mcp_provider(provider_instance_id)
        return McpProbeResponse.model_validate(result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/rescan", response_model=RescanResponse)
async def rescan_tools(
    data: DiscoveredToolsRescanRequest,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Rescan tool sources (full or scoped to one MCP provider)."""
    service = ToolDiscoveryService(db)
    try:
        stats = await service.rescan(
            include_local=data.include_local,
            provider_instance_id=data.provider_instance_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return RescanResponse(
        message="Tool discovery completed",
        stats=stats,
    )


@router.post("/onboard-mcp", response_model=McpOnboardResponse)
async def onboard_mcp_provider(
    data: McpOnboardRequest,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Onboard MCP provider in one deterministic flow."""
    service = ToolDiscoveryService(db)
    try:
        result = await service.onboard_mcp_provider(
            provider_instance_id=data.provider_instance_id,
            enable_all_in_runtime=data.enable_all_in_runtime,
            include_local=data.include_local,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    await db.commit()
    return McpOnboardResponse.model_validate(result)
