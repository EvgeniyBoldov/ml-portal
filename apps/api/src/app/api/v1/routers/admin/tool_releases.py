"""
Admin API endpoints for Tool Groups, Tools, and Releases
"""
import os
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.services.tool_release_service import (
    ToolReleaseService,
    ToolNotFoundError,
    ToolGroupNotFoundError,
    ReleaseNotFoundError,
    BackendReleaseNotFoundError,
    ReleaseNotEditableError,
    ToolGroupHasToolsError,
)
from app.services.tool_sync_service import ToolSyncService
from app.schemas.tool_releases import (
    ToolGroupCreate,
    ToolGroupUpdate,
    ToolGroupResponse,
    ToolGroupDetailResponse,
    ToolGroupListItem,
    ToolResponse,
    ToolDetailResponse,
    ToolListItem,
    ToolBackendReleaseResponse,
    ToolBackendReleaseListItem,
    ToolReleaseCreate,
    ToolReleaseUpdate,
    ToolReleaseResponse,
    ToolReleaseListItem,
    SchemaDiffResponse,
)

router = APIRouter(prefix="/tool-groups", tags=["Tool Groups"])


# ─────────────────────────────────────────────────────────────────────────────
# TOOL GROUPS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("", response_model=List[ToolGroupListItem])
async def list_tool_groups(
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """List all tool groups"""
    service = ToolReleaseService(session)
    groups = await service.list_groups()
    
    return [
        ToolGroupListItem(
            id=g.id,
            slug=g.slug,
            name=g.name,
            description=g.description,
            tools_count=len(g.tools) if g.tools else 0,
            instances_count=len(g.instances) if g.instances else 0,
        )
        for g in groups
    ]


@router.post("", response_model=ToolGroupResponse, status_code=status.HTTP_201_CREATED)
async def create_tool_group(
    data: ToolGroupCreate,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Create a new tool group"""
    service = ToolReleaseService(session)
    try:
        group = await service.create_group(data)
        await session.commit()
        return ToolGroupResponse.model_validate(group)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{slug}", response_model=ToolGroupDetailResponse)
async def get_tool_group(
    slug: str,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get tool group by slug with tools"""
    service = ToolReleaseService(session)
    try:
        group = await service.get_group(slug)
        
        tools = [
            ToolListItem(
                id=t.id,
                slug=t.slug,
                name=t.name,
                description=t.description,
                type=t.type,
                is_active=t.is_active,
                backend_releases_count=len(t.backend_releases) if t.backend_releases else 0,
                releases_count=len(t.releases) if t.releases else 0,
                has_recommended=t.recommended_release_id is not None,
            )
            for t in group.tools
        ]
        
        return ToolGroupDetailResponse(
            id=group.id,
            slug=group.slug,
            name=group.name,
            description=group.description,
            created_at=group.created_at,
            updated_at=group.updated_at,
            tools=tools,
            instances_count=len(group.instances) if group.instances else 0,
        )
    except ToolGroupNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tool group '{slug}' not found")


@router.patch("/{slug}", response_model=ToolGroupResponse)
async def update_tool_group(
    slug: str,
    data: ToolGroupUpdate,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Update a tool group"""
    service = ToolReleaseService(session)
    try:
        group = await service.update_group(slug, data)
        return ToolGroupResponse.model_validate(group)
    except ToolGroupNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tool group '{slug}' not found")


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tool_group(
    slug: str,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Delete a tool group"""
    service = ToolReleaseService(session)
    try:
        await service.delete_group(slug)
    except ToolGroupNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tool group '{slug}' not found")
    except ToolGroupHasToolsError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# TOOLS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{group_slug}/tools", response_model=List[ToolListItem])
async def list_tools_by_group(
    group_slug: str,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """List all tools in a group"""
    service = ToolReleaseService(session)
    try:
        tools = await service.list_tools_by_group(group_slug)
        return [
            ToolListItem(
                id=t.id,
                slug=t.slug,
                name=t.name,
                description=t.description,
                type=t.type,
                is_active=t.is_active,
                backend_releases_count=len(t.backend_releases) if t.backend_releases else 0,
                releases_count=len(t.releases) if t.releases else 0,
                has_recommended=t.recommended_release_id is not None,
            )
            for t in tools
        ]
    except ToolGroupNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tool group '{group_slug}' not found")


# Separate router for tools (without group prefix)
tools_router = APIRouter(prefix="/tools", tags=["Tools"])


@tools_router.get("/{slug}", response_model=ToolDetailResponse)
async def get_tool(
    slug: str,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get tool by slug with releases"""
    service = ToolReleaseService(session)
    try:
        tool = await service.get_tool(slug)
        
        backend_releases = [
            ToolBackendReleaseListItem(
                id=br.id,
                version=br.version,
                description=br.description,
                deprecated=br.deprecated,
                schema_hash=br.schema_hash,
                worker_build_id=br.worker_build_id,
                last_seen_at=br.last_seen_at,
                synced_at=br.synced_at,
            )
            for br in tool.backend_releases
        ]
        
        releases = [
            ToolReleaseListItem(
                id=r.id,
                version=r.version,
                status=r.status,
                backend_release_id=r.backend_release_id,
                backend_version=r.backend_release.version if r.backend_release else None,
                expected_schema_hash=r.expected_schema_hash,
                parent_release_id=r.parent_release_id,
                notes=r.notes,
                created_at=r.created_at,
            )
            for r in tool.releases
        ]
        
        recommended = None
        if tool.recommended_release:
            r = tool.recommended_release
            recommended = ToolReleaseResponse(
                id=r.id,
                tool_id=r.tool_id,
                version=r.version,
                backend_release_id=r.backend_release_id,
                status=r.status,
                config=r.config,
                expected_schema_hash=r.expected_schema_hash,
                parent_release_id=r.parent_release_id,
                notes=r.notes,
                created_at=r.created_at,
                updated_at=r.updated_at,
                backend_release=ToolBackendReleaseListItem(
                    id=r.backend_release.id,
                    version=r.backend_release.version,
                    description=r.backend_release.description,
                    deprecated=r.backend_release.deprecated,
                    schema_hash=r.backend_release.schema_hash,
                    worker_build_id=r.backend_release.worker_build_id,
                    last_seen_at=r.backend_release.last_seen_at,
                    synced_at=r.backend_release.synced_at,
                ) if r.backend_release else None,
            )
        
        return ToolDetailResponse(
            id=tool.id,
            slug=tool.slug,
            name=tool.name,
            description=tool.description,
            type=tool.type,
            tool_group_id=tool.tool_group_id,
            tool_group_slug=tool.tool_group.slug if tool.tool_group else None,
            is_active=tool.is_active,
            recommended_release_id=tool.recommended_release_id,
            created_at=tool.created_at,
            updated_at=tool.updated_at,
            backend_releases=backend_releases,
            releases=releases,
            recommended_release=recommended,
        )
    except ToolNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tool '{slug}' not found")


@tools_router.put("/{slug}/recommended", response_model=ToolDetailResponse)
async def set_recommended_release(
    slug: str,
    release_id: UUID,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Set recommended release for a tool"""
    service = ToolReleaseService(session)
    try:
        tool = await service.set_recommended_release(slug, release_id)
        # Re-fetch with all relations
        return await get_tool(slug, session, _)
    except ToolNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tool '{slug}' not found")
    except ReleaseNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ReleaseNotEditableError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# BACKEND RELEASES (read-only)
# ─────────────────────────────────────────────────────────────────────────────

@tools_router.get("/{slug}/backend-releases", response_model=List[ToolBackendReleaseListItem])
async def list_backend_releases(
    slug: str,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """List all backend releases for a tool"""
    service = ToolReleaseService(session)
    try:
        releases = await service.list_backend_releases(slug)
        return [
            ToolBackendReleaseListItem(
                id=r.id,
                version=r.version,
                description=r.description,
                deprecated=r.deprecated,
                schema_hash=r.schema_hash,
                worker_build_id=r.worker_build_id,
                last_seen_at=r.last_seen_at,
                synced_at=r.synced_at,
            )
            for r in releases
        ]
    except ToolNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tool '{slug}' not found")


@tools_router.get("/{slug}/backend-releases/{version}", response_model=ToolBackendReleaseResponse)
async def get_backend_release(
    slug: str,
    version: str,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get backend release by version"""
    service = ToolReleaseService(session)
    try:
        release = await service.get_backend_release(slug, version)
        return ToolBackendReleaseResponse.model_validate(release)
    except ToolNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tool '{slug}' not found")
    except BackendReleaseNotFoundError:
        raise HTTPException(status_code=404, detail=f"Backend release '{version}' not found")


# ─────────────────────────────────────────────────────────────────────────────
# TOOL RELEASES (CRUD)
# ─────────────────────────────────────────────────────────────────────────────

@tools_router.get("/{slug}/releases", response_model=List[ToolReleaseListItem])
async def list_releases(
    slug: str,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """List all releases for a tool"""
    service = ToolReleaseService(session)
    try:
        releases = await service.list_releases(slug)
        return [
            ToolReleaseListItem(
                id=r.id,
                version=r.version,
                status=r.status,
                backend_release_id=r.backend_release_id,
                backend_version=r.backend_release.version if r.backend_release else None,
                expected_schema_hash=r.expected_schema_hash,
                parent_release_id=r.parent_release_id,
                notes=r.notes,
                created_at=r.created_at,
            )
            for r in releases
        ]
    except ToolNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tool '{slug}' not found")


@tools_router.post("/{slug}/releases", response_model=ToolReleaseResponse, status_code=status.HTTP_201_CREATED)
async def create_release(
    slug: str,
    data: ToolReleaseCreate,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Create a new release (draft)"""
    service = ToolReleaseService(session)
    try:
        release = await service.create_release(slug, data, from_release_id=data.from_release_id)
        return _release_to_response(release)
    except ToolNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tool '{slug}' not found")
    except BackendReleaseNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))


@tools_router.get("/{slug}/releases/{version}", response_model=ToolReleaseResponse)
async def get_release(
    slug: str,
    version: int,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get release by version"""
    service = ToolReleaseService(session)
    try:
        release = await service.get_release(slug, version)
        return _release_to_response(release)
    except ToolNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tool '{slug}' not found")
    except ReleaseNotFoundError:
        raise HTTPException(status_code=404, detail=f"Release v{version} not found")


@tools_router.patch("/{slug}/releases/{version}", response_model=ToolReleaseResponse)
async def update_release(
    slug: str,
    version: int,
    data: ToolReleaseUpdate,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Update a release (only draft)"""
    service = ToolReleaseService(session)
    try:
        release = await service.update_release(slug, version, data)
        return _release_to_response(release)
    except ToolNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tool '{slug}' not found")
    except ReleaseNotFoundError:
        raise HTTPException(status_code=404, detail=f"Release v{version} not found")
    except ReleaseNotEditableError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except BackendReleaseNotFoundError as e:
        raise HTTPException(status_code=400, detail=str(e))


@tools_router.post("/{slug}/releases/{version}/activate", response_model=ToolReleaseResponse)
async def activate_release(
    slug: str,
    version: int,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Activate a release"""
    service = ToolReleaseService(session)
    try:
        release = await service.activate_release(slug, version)
        return _release_to_response(release)
    except ToolNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tool '{slug}' not found")
    except ReleaseNotFoundError:
        raise HTTPException(status_code=404, detail=f"Release v{version} not found")
    except ReleaseNotEditableError as e:
        raise HTTPException(status_code=400, detail=str(e))


@tools_router.post("/{slug}/releases/{version}/archive", response_model=ToolReleaseResponse)
async def archive_release(
    slug: str,
    version: int,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Archive a release"""
    service = ToolReleaseService(session)
    try:
        release = await service.archive_release(slug, version)
        return _release_to_response(release)
    except ToolNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tool '{slug}' not found")
    except ReleaseNotFoundError:
        raise HTTPException(status_code=404, detail=f"Release v{version} not found")
    except ReleaseNotEditableError as e:
        raise HTTPException(status_code=400, detail=str(e))


def _release_to_response(release) -> ToolReleaseResponse:
    """Convert release model to response"""
    backend_release = None
    if release.backend_release:
        backend_release = ToolBackendReleaseListItem(
            id=release.backend_release.id,
            version=release.backend_release.version,
            description=release.backend_release.description,
            deprecated=release.backend_release.deprecated,
            schema_hash=release.backend_release.schema_hash,
            worker_build_id=release.backend_release.worker_build_id,
            last_seen_at=release.backend_release.last_seen_at,
            synced_at=release.backend_release.synced_at,
        )
    
    return ToolReleaseResponse(
        id=release.id,
        tool_id=release.tool_id,
        version=release.version,
        backend_release_id=release.backend_release_id,
        status=release.status,
        config=release.config,
        description_for_llm=release.description_for_llm,
        category=release.category,
        tags=release.tags or [],
        field_hints=release.field_hints or {},
        examples=release.examples or [],
        return_summary=release.return_summary,
        meta_hash=release.meta_hash,
        expected_schema_hash=release.expected_schema_hash,
        parent_release_id=release.parent_release_id,
        notes=release.notes,
        created_at=release.created_at,
        updated_at=release.updated_at,
        backend_release=backend_release,
    )


# ─────────────────────────────────────────────────────────────────────────────
# SCHEMA DIFF
# ─────────────────────────────────────────────────────────────────────────────

@tools_router.get("/{slug}/schema-diff", response_model=SchemaDiffResponse)
async def get_schema_diff(
    slug: str,
    from_backend_release_id: UUID,
    to_backend_release_id: UUID,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get schema diff between two backend releases"""
    service = ToolReleaseService(session)
    try:
        diff = await service.get_schema_diff(slug, from_backend_release_id, to_backend_release_id)
        return SchemaDiffResponse(**diff)
    except ToolNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tool '{slug}' not found")
    except BackendReleaseNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# SYNC / RESCAN ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/rescan", status_code=status.HTTP_200_OK)
async def rescan_all_tools(
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Rescan all tools from registry and sync to DB (tools + backend releases)"""
    sync_service = ToolSyncService(session, worker_build_id=os.getenv("WORKER_BUILD_ID"))
    stats = await sync_service.sync_all()
    return {
        "message": "Tools synced successfully",
        "stats": stats,
    }


@router.post("/{group_slug}/rescan", status_code=status.HTTP_200_OK)
async def rescan_group_tools(
    group_slug: str,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Rescan tools in a specific group from registry"""
    service = ToolReleaseService(session)
    sync_service = ToolSyncService(session, worker_build_id=os.getenv("WORKER_BUILD_ID"))
    
    try:
        group = await service.get_group(group_slug)
        stats = await sync_service.sync_all()
        
        return {
            "message": f"Tools in group '{group_slug}' synced successfully",
            "stats": stats,
            "group_id": str(group.id),
        }
    except ToolGroupNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tool group '{group_slug}' not found")


@tools_router.post("/{slug}/rescan-backend", status_code=status.HTTP_200_OK)
async def rescan_backend_releases(
    slug: str,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Rescan backend releases for a specific tool"""
    service = ToolReleaseService(session)
    
    try:
        tool = await service.get_tool(slug)
        
        # Sync tools + backend releases from registry
        sync_service = ToolSyncService(session, worker_build_id=os.getenv("WORKER_BUILD_ID"))
        stats = await sync_service.sync_all()
        
        # Re-fetch tool with updated backend releases
        updated_tool = await service.get_tool(slug)
        
        backend_releases = [
            ToolBackendReleaseListItem(
                id=br.id,
                version=br.version,
                description=br.description,
                deprecated=br.deprecated,
                schema_hash=br.schema_hash,
                worker_build_id=br.worker_build_id,
                last_seen_at=br.last_seen_at,
                synced_at=br.synced_at,
            )
            for br in updated_tool.backend_releases
        ]
        
        return {
            "message": f"Backend releases for tool '{slug}' synced successfully",
            "stats": stats,
            "backend_releases": backend_releases,
        }
    except ToolNotFoundError:
        raise HTTPException(status_code=404, detail=f"Tool '{slug}' not found")
