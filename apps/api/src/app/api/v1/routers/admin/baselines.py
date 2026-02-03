"""
Admin API endpoints for Baseline management.
Baseline is a separate entity from Prompt for managing restrictions and rules.
"""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.schemas.baselines import (
    BaselineContainerCreate,
    BaselineContainerUpdate,
    BaselineContainerResponse,
    BaselineVersionCreate,
    BaselineVersionUpdate,
    BaselineVersionResponse,
    BaselineVersionInfo,
    BaselineListItem,
    BaselineDetailResponse,
    EffectiveBaselinesRequest,
    EffectiveBaselinesResponse,
    EffectiveBaselineItem,
)
from app.services.baseline_service import BaselineService
from app.core.exceptions import NotFoundException, ValidationException


router = APIRouter(tags=["Admin: Baselines"])


# ─────────────────────────────────────────────────────────────────────────────
# BASELINE CONTAINER endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("", response_model=BaselineContainerResponse, status_code=201)
async def create_baseline_container(
    data: BaselineContainerCreate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Create new baseline container. Admin only."""
    service = BaselineService(db)
    try:
        baseline = await service.create_baseline(
            slug=data.slug,
            name=data.name,
            description=data.description,
            scope=data.scope,
            tenant_id=data.tenant_id,
            user_id=data.user_id,
            is_active=data.is_active,
        )
        await db.commit()
        return baseline
    except ValidationException as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=List[BaselineListItem])
async def list_baselines(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    scope: Optional[str] = Query(None, description="Filter by scope: default, tenant, user"),
    tenant_id: Optional[UUID] = Query(None, description="Filter by tenant"),
    user_id: Optional[UUID] = Query(None, description="Filter by user"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """List all baseline containers. Admin only."""
    service = BaselineService(db)
    baselines, total = await service.list_baselines(
        skip, limit, scope, tenant_id, user_id, is_active
    )
    
    # Convert to list items with version info
    items = []
    for baseline in baselines:
        latest_version = await service.version_repo.get_latest_by_baseline(baseline.id)
        active_version = await service.version_repo.get_active_by_baseline(baseline.id)
        versions = await service.version_repo.get_all_by_baseline(baseline.id)
        
        items.append(BaselineListItem(
            id=baseline.id,
            slug=baseline.slug,
            name=baseline.name,
            description=baseline.description,
            scope=baseline.scope,
            tenant_id=baseline.tenant_id,
            user_id=baseline.user_id,
            is_active=baseline.is_active,
            versions_count=len(versions),
            latest_version=latest_version.version if latest_version else None,
            active_version=active_version.version if active_version else None,
            updated_at=baseline.updated_at
        ))
    
    return items


@router.get("/effective", response_model=EffectiveBaselinesResponse)
async def get_effective_baselines(
    tenant_id: Optional[UUID] = Query(None, description="Tenant ID"),
    user_id: Optional[UUID] = Query(None, description="User ID"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """
    Get effective baselines for a user/tenant.
    Resolution priority: User > Tenant > Default.
    Returns all applicable baselines merged.
    """
    service = BaselineService(db)
    
    baselines = await service.get_effective_baselines(tenant_id, user_id)
    merged_content = await service.get_merged_baseline_content(tenant_id, user_id)
    
    items = []
    for baseline in baselines:
        active_version = await service.version_repo.get_active_by_baseline(baseline.id)
        if active_version:
            items.append(EffectiveBaselineItem(
                id=baseline.id,
                slug=baseline.slug,
                name=baseline.name,
                scope=baseline.scope,
                template=active_version.template,
            ))
    
    return EffectiveBaselinesResponse(
        baselines=items,
        merged_content=merged_content,
    )


@router.get("/{slug}", response_model=BaselineDetailResponse)
async def get_baseline_detail(
    slug: str = Path(..., description="Baseline slug"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get baseline container with all versions. Admin only."""
    service = BaselineService(db)
    try:
        baseline = await service.get_baseline_by_slug(slug)
        versions = await service.get_versions(slug)
        
        return BaselineDetailResponse(
            id=baseline.id,
            slug=baseline.slug,
            name=baseline.name,
            description=baseline.description,
            scope=baseline.scope,
            tenant_id=baseline.tenant_id,
            user_id=baseline.user_id,
            is_active=baseline.is_active,
            created_at=baseline.created_at,
            updated_at=baseline.updated_at,
            versions=[BaselineVersionInfo.model_validate(v) for v in versions]
        )
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/{slug}", response_model=BaselineContainerResponse)
async def update_baseline_container(
    slug: str = Path(..., description="Baseline slug"),
    data: BaselineContainerUpdate = ...,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Update baseline container metadata. Admin only."""
    service = BaselineService(db)
    try:
        baseline = await service.get_baseline_by_slug(slug)
        updated = await service.update_baseline(
            baseline_id=baseline.id,
            name=data.name,
            description=data.description,
            is_active=data.is_active,
        )
        await db.commit()
        return updated
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{slug}", status_code=204)
async def delete_baseline_container(
    slug: str = Path(..., description="Baseline slug"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Delete baseline container and all versions. Admin only."""
    service = BaselineService(db)
    try:
        baseline = await service.get_baseline_by_slug(slug)
        await service.delete_baseline(baseline.id)
        await db.commit()
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# BASELINE VERSION endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{slug}/versions", response_model=BaselineVersionResponse, status_code=201)
async def create_baseline_version(
    slug: str = Path(..., description="Baseline slug"),
    data: BaselineVersionCreate = ...,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Create new version for a baseline. Admin only."""
    service = BaselineService(db)
    try:
        version = await service.create_version(
            slug=slug,
            template=data.template,
            parent_version_id=data.parent_version_id,
            notes=data.notes,
        )
        await db.commit()
        return version
    except (NotFoundException, ValidationException) as e:
        status_code = 404 if isinstance(e, NotFoundException) else 400
        raise HTTPException(status_code=status_code, detail=str(e))


@router.get("/{slug}/versions", response_model=List[BaselineVersionInfo])
async def list_baseline_versions(
    slug: str = Path(..., description="Baseline slug"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """List all versions of a baseline. Admin only."""
    service = BaselineService(db)
    try:
        versions = await service.get_versions(slug)
        return [BaselineVersionInfo.model_validate(v) for v in versions]
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{slug}/versions/{version_id}", response_model=BaselineVersionResponse)
async def get_baseline_version(
    slug: str = Path(..., description="Baseline slug"),
    version_id: UUID = Path(..., description="Version ID"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get specific version of a baseline. Admin only."""
    service = BaselineService(db)
    try:
        version = await service.get_version(version_id)
        return version
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/{slug}/versions/{version_id}", response_model=BaselineVersionResponse)
async def update_baseline_version(
    slug: str = Path(..., description="Baseline slug"),
    version_id: UUID = Path(..., description="Version ID"),
    data: BaselineVersionUpdate = ...,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Update draft version. Admin only."""
    service = BaselineService(db)
    try:
        version = await service.update_version(
            version_id=version_id,
            template=data.template,
            notes=data.notes,
        )
        await db.commit()
        return version
    except (NotFoundException, ValidationException) as e:
        status_code = 404 if isinstance(e, NotFoundException) else 400
        raise HTTPException(status_code=status_code, detail=str(e))


@router.post("/{slug}/versions/{version_id}/activate", response_model=BaselineVersionResponse)
async def activate_baseline_version(
    slug: str = Path(..., description="Baseline slug"),
    version_id: UUID = Path(..., description="Version ID"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Activate a draft version. Admin only."""
    service = BaselineService(db)
    try:
        version = await service.activate_version(version_id)
        await db.commit()
        return version
    except (NotFoundException, ValidationException) as e:
        status_code = 404 if isinstance(e, NotFoundException) else 400
        raise HTTPException(status_code=status_code, detail=str(e))


@router.post("/{slug}/versions/{version_id}/archive", response_model=BaselineVersionResponse)
async def archive_baseline_version(
    slug: str = Path(..., description="Baseline slug"),
    version_id: UUID = Path(..., description="Version ID"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Archive a version. Admin only."""
    service = BaselineService(db)
    try:
        version = await service.archive_version(version_id)
        await db.commit()
        return version
    except (NotFoundException, ValidationException) as e:
        status_code = 404 if isinstance(e, NotFoundException) else 400
        raise HTTPException(status_code=status_code, detail=str(e))


@router.put("/{slug}/recommended", response_model=BaselineDetailResponse)
async def set_recommended_version(
    slug: str = Path(..., description="Baseline slug"),
    version_id: UUID = Query(..., description="Version ID to set as recommended"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Set the recommended version for a baseline. Version must be active. Admin only."""
    service = BaselineService(db)
    try:
        baseline = await service.update_recommended_version(slug, version_id)
        await db.commit()
        return baseline
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValidationException as e:
        raise HTTPException(status_code=400, detail=str(e))
