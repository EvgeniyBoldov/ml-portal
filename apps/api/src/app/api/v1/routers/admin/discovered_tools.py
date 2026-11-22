"""Discovered tools admin API."""
from typing import List, Optional
from uuid import NAMESPACE_URL, UUID, uuid5

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.agents.registry import ToolRegistry
from app.agents.runtime.result_workspace_tools import WORKSPACE_TOOLS
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


def _display_metadata(tool: DiscoveredTool, source_types: list[str]) -> dict[str, object]:
    provider = tool.provider_instance
    return {
        "connector_slug": provider.slug if provider else None,
        "connector_name": provider.name if provider else None,
        "has_observed_data_schema": tool.observed_data_schema is not None,
        "source_types": source_types,
    }


def _workspace_catalog() -> list[DiscoveredToolDetailResponse]:
    entries = [
        DiscoveredToolDetailResponse(
            id=uuid5(NAMESPACE_URL, f"ml-portal:runtime-workspace:{slug}"),
            slug=slug,
            name=slug,
            description=description,
            source="local",
            domains=["system"],
            source_types=["system"],
            input_schema=model.model_json_schema(),
            runtime_managed=True,
        )
        for slug, (model, description) in WORKSPACE_TOOLS.items()
    ]
    analyze = ToolRegistry.get("result.analyze")
    if analyze is not None:
        descriptor = analyze.to_mcp_descriptor()
        entries.append(DiscoveredToolDetailResponse(
            id=uuid5(NAMESPACE_URL, "ml-portal:runtime-workspace:result.analyze"),
            slug=analyze.slug,
            name=analyze.name,
            description=descriptor.get("description"),
            source="local",
            domains=["system"],
            source_types=["system"],
            input_schema=descriptor.get("inputSchema"),
            output_schema=descriptor.get("outputSchema"),
            runtime_managed=True,
        ))
    return entries


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
    source_types = await service.source_types_for(tools)
    items = [
        DiscoveredToolListItem.model_validate(tool).model_copy(
            update=_display_metadata(tool, source_types.get(tool.id, []))
        )
        for tool in tools
    ]
    if source in (None, "local") and provider_instance_id is None and domain in (None, "system") and is_active is not False:
        local_slugs = {item.slug for item in items if item.source == "local" and item.provider_instance_id is None}
        items.extend(item for item in _workspace_catalog() if item.slug not in local_slugs)
        items.sort(key=lambda item: item.slug)
    return items


@router.get("/{tool_id}", response_model=DiscoveredToolDetailResponse)
async def get_discovered_tool(
    tool_id: UUID,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get discovered tool detail by UUID."""
    for item in _workspace_catalog():
        if item.id == tool_id:
            return item
    stmt = (
        select(DiscoveredTool)
        .options(selectinload(DiscoveredTool.tool), selectinload(DiscoveredTool.provider_instance))
        .where(DiscoveredTool.id == tool_id)
    )
    result = await db.execute(stmt)
    tool = result.scalar_one_or_none()
    if not tool:
        raise HTTPException(status_code=404, detail=f"Discovered tool '{tool_id}' not found")
    source_types = await ToolDiscoveryService(db).source_types_for([tool])
    return DiscoveredToolDetailResponse.model_validate(tool).model_copy(
        update=_display_metadata(tool, source_types.get(tool.id, []))
    )


@router.patch("/{tool_id}", response_model=DiscoveredToolDetailResponse)
async def update_discovered_tool(
    tool_id: UUID,
    data: DiscoveredToolUpdateRequest,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Update discovered capability metadata."""
    if any(item.id == tool_id for item in _workspace_catalog()):
        raise HTTPException(status_code=409, detail="Runtime workspace operations are managed by the runtime.")
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

    if "risk_level" in data.model_fields_set:
        tool.risk_level = data.risk_level.strip() if data.risk_level and data.risk_level.strip() else None

    if "result_delivery" in data.model_fields_set and data.result_delivery is not None:
        tool.result_delivery = data.result_delivery

    await db.flush()
    await db.refresh(tool)
    source_types = await ToolDiscoveryService(db).source_types_for([tool])
    result_item = DiscoveredToolDetailResponse.model_validate(tool).model_copy(
        update=_display_metadata(tool, source_types.get(tool.id, []))
    )
    await db.commit()
    return result_item


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
