"""
Admin API endpoints for Tools, Releases, and Backend Releases.

Subresources:
- GET/PUT /{tool_id}                          — tool detail + current-version
- GET/POST /{tool_id}/releases                — releases CRUD
- GET/PATCH /{tool_id}/releases/{version}     — release detail/update
- POST /{tool_id}/releases/{version}/activate|archive
- GET /{tool_id}/backend-releases             — read-only backend releases
- GET /{tool_id}/schema-diff                  — diff between backend releases
- POST /{tool_id}/rescan-backend              — rescan backend releases
"""
import os
from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.services.tool_release_service import ToolReleaseService
from app.services.tool_service import ToolService
from app.services.tool_backend_release_sync_service import ToolBackendReleaseSyncService
from app.schemas.tool_releases import (
    ToolReleaseCreate,
    ToolReleaseUpdate,
    ToolReleaseResponse,
    ToolReleaseListItem,
    SchemaDiffResponse,
    ToolBackendReleaseResponse,
    ToolBackendReleaseListItem,
)
from app.schemas.tools import ToolDetailResponse, ToolListItem, ToolCreate
from app.schemas.tools import ToolUpdate


router = APIRouter(tags=["tools"])


@router.get("", response_model=List[ToolListItem])
async def list_tools(
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """List all tool containers."""
    tools, _ = await ToolService(db).list_tools()
    return [
        ToolListItem(
            id=t.id,
            slug=t.slug,
            name=t.name,
            domains=t.domains or [],
            tags=t.tags,
            current_version_id=t.current_version_id,
            has_current_version=bool(t.current_version_id),
            created_at=t.created_at,
        )
        for t in tools
    ]


@router.post("", response_model=ToolDetailResponse, status_code=status.HTTP_201_CREATED)
async def create_tool(
    data: ToolCreate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Create a new tool publication container."""
    tool = await ToolService(db).create_tool(data)
    await db.commit()
    await db.refresh(tool)
    return await ToolReleaseService(db).get_tool_by_id(tool.id)


@router.get("/{tool_id}", response_model=ToolDetailResponse)
async def get_tool(
    tool_id: UUID,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get tool by UUID with enriched data (domains, releases)."""
    service = ToolReleaseService(session)
    tool = await service.get_tool_by_id(tool_id)

    current_release = None
    if tool.current_version_id:
        current_release = next(
            (r for r in tool.releases if r.id == tool.current_version_id), None
        )

    return ToolDetailResponse(
        id=tool.id,
        slug=tool.slug,
        name=tool.name,
        domains=tool.domains or [],
        tags=tool.tags,
        current_version_id=tool.current_version_id,
        created_at=tool.created_at,
        backend_releases=[
            ToolBackendReleaseListItem.model_validate(br)
            for br in tool.backend_releases
        ],
        releases=[
            ToolReleaseListItem.model_validate(r)
            for r in tool.releases
        ],
        current_version=(
            ToolReleaseResponse.model_validate(current_release)
            if current_release else None
        ),
    )


@router.patch("/{tool_id}", response_model=ToolDetailResponse)
async def update_tool(
    tool_id: UUID,
    data: ToolUpdate,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Update mutable tool container fields."""
    tool_service = ToolService(session)
    release_service = ToolReleaseService(session)
    await tool_service.update_tool(tool_id, data)
    await session.commit()
    tool = await release_service.get_tool_by_id(tool_id)

    current_release = None
    if tool.current_version_id:
        current_release = next(
            (r for r in tool.releases if r.id == tool.current_version_id), None
        )

    return ToolDetailResponse(
        id=tool.id,
        slug=tool.slug,
        name=tool.name,
        domains=tool.domains or [],
        tags=tool.tags,
        current_version_id=tool.current_version_id,
        created_at=tool.created_at,
        backend_releases=[
            ToolBackendReleaseListItem.model_validate(br)
            for br in tool.backend_releases
        ],
        releases=[
            ToolReleaseListItem.model_validate(r)
            for r in tool.releases
        ],
        current_version=(
            ToolReleaseResponse.model_validate(current_release)
            if current_release else None
        ),
    )


@router.put("/{tool_id}/current-version", response_model=ToolDetailResponse)
async def set_current_version(
    tool_id: UUID,
    release_id: UUID,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Set current version for a tool"""
    service = ToolReleaseService(session)
    await service.set_current_version_by_id(tool_id, release_id)
    return await get_tool(tool_id, session, _)


# ─────────────────────────────────────────────────────────────────────────────
# BACKEND RELEASES (read-only)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{tool_id}/backend-releases", response_model=List[ToolBackendReleaseListItem])
async def list_backend_releases(
    tool_id: UUID,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """List all backend releases for a tool"""
    service = ToolReleaseService(session)
    releases = await service.list_backend_releases_by_tool_id(tool_id)
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


@router.get("/{tool_id}/backend-releases/{version}", response_model=ToolBackendReleaseResponse)
async def get_backend_release(
    tool_id: UUID,
    version: str,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get backend release by version"""
    service = ToolReleaseService(session)
    release = await service.get_backend_release_by_tool_id(tool_id, version)
    return ToolBackendReleaseResponse.model_validate(release)


# ─────────────────────────────────────────────────────────────────────────────
# TOOL RELEASES (CRUD)
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{tool_id}/releases", response_model=List[ToolReleaseListItem])
async def list_releases(
    tool_id: UUID,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """List all releases for a tool"""
    service = ToolReleaseService(session)
    releases = await service.list_releases_by_tool_id(tool_id)
    return [
        ToolReleaseListItem(
            id=r.id,
            version=r.version,
            status=r.status,
            backend_release_id=r.backend_release_id,
            backend_version=r.backend_release.version if r.backend_release else None,
            expected_schema_hash=r.expected_schema_hash,
            parent_release_id=r.parent_release_id,
            created_at=r.created_at,
        )
        for r in releases
    ]


@router.post("/{tool_id}/releases", response_model=ToolReleaseResponse, status_code=status.HTTP_201_CREATED)
async def create_release(
    tool_id: UUID,
    data: ToolReleaseCreate,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Create a new release (draft)"""
    service = ToolReleaseService(session)
    release = await service.create_release_by_tool_id(tool_id, data, from_release_id=data.from_release_id)
    return _release_to_response(release)


@router.get("/{tool_id}/releases/{version}", response_model=ToolReleaseResponse)
async def get_release(
    tool_id: UUID,
    version: int,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get release by version"""
    service = ToolReleaseService(session)
    release = await service.get_release_by_tool_id(tool_id, version)
    return _release_to_response(release)


@router.patch("/{tool_id}/releases/{version}", response_model=ToolReleaseResponse)
async def update_release(
    tool_id: UUID,
    version: int,
    data: ToolReleaseUpdate,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Update release"""
    service = ToolReleaseService(session)
    release = await service.update_release_by_tool_id(tool_id, version, data)
    return _release_to_response(release)


@router.post("/{tool_id}/releases/{version}/activate", response_model=ToolReleaseResponse)
async def activate_release(
    tool_id: UUID,
    version: int,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Activate a release"""
    service = ToolReleaseService(session)
    release = await service.activate_release_by_tool_id(tool_id, version)
    return _release_to_response(release)


@router.post("/{tool_id}/releases/{version}/archive", response_model=ToolReleaseResponse)
async def archive_release(
    tool_id: UUID,
    version: int,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Archive a release"""
    service = ToolReleaseService(session)
    release = await service.archive_release_by_tool_id(tool_id, version)
    return _release_to_response(release)


@router.delete("/{tool_id}/releases/{version}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_release(
    tool_id: UUID,
    version: int,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Delete a release."""
    service = ToolReleaseService(session)
    await service.delete_release_by_tool_id(tool_id, version)


def _release_to_response(release) -> ToolReleaseResponse:
    """Convert release model to response"""
    backend_release = None
    if release.backend_release:
        backend_release = ToolBackendReleaseResponse(
            id=release.backend_release.id,
            tool_id=release.backend_release.tool_id,
            version=release.backend_release.version,
            input_schema=release.backend_release.input_schema or {},
            output_schema=release.backend_release.output_schema,
            description=release.backend_release.description,
            method_name=release.backend_release.method_name,
            deprecated=release.backend_release.deprecated,
            deprecation_message=release.backend_release.deprecation_message,
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
        semantic_profile=release.semantic_profile or {},
        policy_hints=release.policy_hints or {},
        # Meta
        meta_hash=release.meta_hash,
        expected_schema_hash=release.expected_schema_hash,
        parent_release_id=release.parent_release_id,
        created_at=release.created_at,
        updated_at=release.updated_at,
        backend_release=backend_release,
    )


# ─────────────────────────────────────────────────────────────────────────────
# SCHEMA DIFF
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{tool_id}/schema-diff", response_model=SchemaDiffResponse)
async def get_schema_diff(
    tool_id: UUID,
    from_backend_release_id: UUID,
    to_backend_release_id: UUID,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get schema diff between two backend releases by tool UUID"""
    service = ToolReleaseService(session)
    diff = await service.get_schema_diff_by_tool_id(tool_id, from_backend_release_id, to_backend_release_id)
    return SchemaDiffResponse(**diff)


# ─────────────────────────────────────────────────────────────────────────────
# SYNC / RESCAN ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/{tool_id}/rescan-backend", status_code=status.HTTP_200_OK)
async def rescan_backend_releases(
    tool_id: UUID,
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Rescan backend releases for a specific tool by UUID"""
    service = ToolReleaseService(session)

    tool = await service.get_tool_by_id(tool_id)

    sync_service = ToolBackendReleaseSyncService(session, worker_build_id=os.getenv("WORKER_BUILD_ID"))
    stats = await sync_service.sync_backend_releases(tool_slug=tool.slug)
    await session.commit()

    updated_tool = await service.get_tool_by_id(tool_id)

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
        "message": f"Backend releases for tool '{tool.slug}' synced successfully",
        "stats": stats,
        "backend_releases": backend_releases,
    }
