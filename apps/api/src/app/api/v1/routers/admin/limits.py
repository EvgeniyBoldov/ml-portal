"""
Limits Admin API - execution limits with versioning support.

Architecture:
- Limit (container) - holds metadata: slug, name, description
- LimitVersion - holds versioned data: max_steps, timeouts, etc.
- current_version_id - points to the active version

Version workflow:
- Create → always draft
- Activate → draft → active (deprecates previous active)
- Deactivate → draft or active → deprecated
"""
from typing import List, Optional
from uuid import UUID
from fastapi import APIRouter, Depends, Query, Path, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.schemas.limits import (
    LimitContainerCreate,
    LimitContainerUpdate,
    LimitContainerResponse,
    LimitVersionCreate,
    LimitVersionUpdate,
    LimitVersionResponse,
    LimitVersionInfo,
    LimitListItem,
    LimitDetailResponse,
)
from app.services.limit_service import (
    LimitService,
    LimitError,
    LimitNotFoundError,
    LimitVersionNotFoundError,
    LimitAlreadyExistsError,
    LimitVersionNotEditableError,
)

router = APIRouter(tags=["limits"])


# ─────────────────────────────────────────────────────────────────────────────
# LIMIT CONTAINER ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("", response_model=List[LimitListItem])
async def list_limits(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """List all limits. Admin only."""
    service = LimitService(db)
    limits, _ = await service.list_limits(skip=skip, limit=limit)

    items = []
    for lim in limits:
        latest_version = await service.version_repo.get_latest_by_limit(lim.id)
        active_version = await service.version_repo.get_active_by_limit(lim.id)
        versions = await service.version_repo.get_all_by_limit(lim.id)

        items.append(LimitListItem(
            id=lim.id,
            slug=lim.slug,
            name=lim.name,
            description=lim.description,
            current_version_id=lim.current_version_id,
            versions_count=len(versions),
            latest_version=latest_version.version if latest_version else None,
            active_version=active_version.version if active_version else None,
            updated_at=lim.updated_at,
        ))

    return items


@router.post("", response_model=LimitContainerResponse, status_code=status.HTTP_201_CREATED)
async def create_limit(
    data: LimitContainerCreate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Create a new limit container. Admin only."""
    service = LimitService(db)
    try:
        lim = await service.create_limit(
            slug=data.slug,
            name=data.name,
            description=data.description,
        )
        await db.commit()
        return lim
    except LimitAlreadyExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except LimitError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{slug}", response_model=LimitDetailResponse)
async def get_limit(
    slug: str = Path(..., description="Limit slug"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get limit by slug with all versions. Admin only."""
    service = LimitService(db)
    try:
        lim = await service.get_limit_with_versions(slug)
        versions = await service.list_versions(slug)

        current = None
        if lim.current_version_id:
            cv = await service.version_repo.get_by_id(lim.current_version_id)
            if cv:
                current = LimitVersionInfo.model_validate(cv)

        return LimitDetailResponse(
            id=lim.id,
            slug=lim.slug,
            name=lim.name,
            description=lim.description,
            created_at=lim.created_at,
            updated_at=lim.updated_at,
            current_version_id=lim.current_version_id,
            current_version=current,
            versions=[LimitVersionInfo.model_validate(v) for v in versions],
        )
    except LimitNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{slug}", response_model=LimitContainerResponse)
async def update_limit(
    data: LimitContainerUpdate,
    slug: str = Path(..., description="Limit slug"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Update limit container metadata. Admin only."""
    service = LimitService(db)
    try:
        lim = await service.get_limit_by_slug(slug)
        lim = await service.update_limit(
            limit_id=lim.id,
            name=data.name,
            description=data.description,
        )
        await db.commit()
        return lim
    except LimitNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except LimitError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{slug}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_limit(
    slug: str = Path(..., description="Limit slug"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Delete limit and all its versions. Admin only."""
    service = LimitService(db)
    try:
        lim = await service.get_limit_by_slug(slug)
        await service.delete_limit(lim.id)
        await db.commit()
    except LimitNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except LimitError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# LIMIT VERSION ENDPOINTS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/{slug}/versions", response_model=List[LimitVersionResponse])
async def list_versions(
    slug: str = Path(..., description="Limit slug"),
    status_filter: Optional[str] = Query(None, description="Filter by status: draft, active, deprecated"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """List all versions of a limit. Admin only."""
    service = LimitService(db)
    try:
        versions = await service.list_versions(slug, status_filter)
        return versions
    except LimitNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{slug}/versions", response_model=LimitVersionResponse, status_code=status.HTTP_201_CREATED)
async def create_version(
    data: LimitVersionCreate,
    slug: str = Path(..., description="Limit slug"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Create a new version for a limit (always in draft status). Admin only."""
    service = LimitService(db)
    try:
        version = await service.create_version(
            limit_slug=slug,
            max_steps=data.max_steps,
            max_tool_calls=data.max_tool_calls,
            max_wall_time_ms=data.max_wall_time_ms,
            tool_timeout_ms=data.tool_timeout_ms,
            max_retries=data.max_retries,
            extra_config=data.extra_config,
            notes=data.notes,
            parent_version_id=data.parent_version_id,
        )
        await db.commit()
        return version
    except LimitNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except LimitError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{slug}/versions/{version_number}", response_model=LimitVersionResponse)
async def get_version(
    slug: str = Path(..., description="Limit slug"),
    version_number: int = Path(..., description="Version number"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get specific version of a limit. Admin only."""
    service = LimitService(db)
    try:
        version = await service.get_version_by_number(slug, version_number)
        return version
    except (LimitNotFoundError, LimitVersionNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/{slug}/versions/{version_number}", response_model=LimitVersionResponse)
async def update_version(
    data: LimitVersionUpdate,
    slug: str = Path(..., description="Limit slug"),
    version_number: int = Path(..., description="Version number"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Update a version (only draft versions can be edited). Admin only."""
    service = LimitService(db)
    try:
        version = await service.get_version_by_number(slug, version_number)
        version = await service.update_version(
            version_id=version.id,
            max_steps=data.max_steps,
            max_tool_calls=data.max_tool_calls,
            max_wall_time_ms=data.max_wall_time_ms,
            tool_timeout_ms=data.tool_timeout_ms,
            max_retries=data.max_retries,
            extra_config=data.extra_config,
            notes=data.notes,
        )
        await db.commit()
        return version
    except (LimitNotFoundError, LimitVersionNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except LimitVersionNotEditableError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LimitError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{slug}/versions/{version_number}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_version(
    slug: str = Path(..., description="Limit slug"),
    version_number: int = Path(..., description="Version number"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Delete a version (only draft and deprecated versions). Admin only."""
    service = LimitService(db)
    try:
        version = await service.get_version_by_number(slug, version_number)
        await service.delete_version(version.id)
        await db.commit()
    except (LimitNotFoundError, LimitVersionNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except LimitError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{slug}/versions/{version_number}/activate", response_model=LimitVersionResponse)
async def activate_version(
    slug: str = Path(..., description="Limit slug"),
    version_number: int = Path(..., description="Version number"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """
    Activate a version (draft → active).
    Deprecates the currently active version.
    Updates current_version_id on the limit.
    Admin only.
    """
    service = LimitService(db)
    try:
        version = await service.get_version_by_number(slug, version_number)
        version = await service.activate_version(version.id)
        await db.commit()
        return version
    except (LimitNotFoundError, LimitVersionNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except LimitError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{slug}/versions/{version_number}/deactivate", response_model=LimitVersionResponse)
async def deactivate_version(
    slug: str = Path(..., description="Limit slug"),
    version_number: int = Path(..., description="Version number"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Deactivate a version (draft or active → deprecated). Admin only."""
    service = LimitService(db)
    try:
        version = await service.get_version_by_number(slug, version_number)
        version = await service.deactivate_version(version.id)
        await db.commit()
        return version
    except (LimitNotFoundError, LimitVersionNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))
    except LimitError as e:
        raise HTTPException(status_code=400, detail=str(e))
