from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.schemas.prompts import (
    PromptContainerCreate,
    PromptContainerUpdate,
    PromptContainerResponse,
    PromptVersionCreate,
    PromptVersionUpdate,
    PromptVersionActivate,
    PromptVersionResponse,
    PromptVersionInfo,
    PromptListItem,
    PromptDetailResponse,
    PromptRenderRequest,
    PromptRenderResponse,
)
from app.services.prompt_service import PromptService
from app.core.exceptions import NotFoundException, ValidationException


router = APIRouter(tags=["Admin: Prompts"])


# ─────────────────────────────────────────────────────────────────────────────
# PROMPT CONTAINER endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("", response_model=PromptContainerResponse, status_code=201)
async def create_prompt_container(
    data: PromptContainerCreate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Create new prompt container. Admin only."""
    service = PromptService(db)
    try:
        prompt = await service.create_prompt(
            slug=data.slug,
            name=data.name,
            description=data.description,
            type=data.type
        )
        await db.commit()
        return prompt
    except ValidationException as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=List[PromptListItem])
async def list_prompts(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    type: Optional[str] = Query(None, description="Filter by type: prompt or baseline"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """List all prompt containers. Admin only."""
    service = PromptService(db)
    prompts, total = await service.list_prompts(skip, limit, type)
    
    # Convert to list items with version info
    items = []
    for prompt in prompts:
        latest_version = await service.version_repo.get_latest_by_prompt(prompt.id)
        active_version = await service.version_repo.get_active_by_prompt(prompt.id)
        versions = await service.version_repo.get_all_by_prompt(prompt.id)
        
        items.append(PromptListItem(
            id=prompt.id,
            slug=prompt.slug,
            name=prompt.name,
            description=prompt.description,
            type=prompt.type,
            versions_count=len(versions),
            latest_version=latest_version.version if latest_version else None,
            active_version=active_version.version if active_version else None,
            updated_at=prompt.updated_at
        ))
    
    return items


@router.get("/{slug}", response_model=PromptDetailResponse)
async def get_prompt_detail(
    slug: str = Path(..., description="Prompt slug"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get prompt container with all versions. Admin only."""
    service = PromptService(db)
    try:
        prompt = await service.get_prompt_by_slug(slug)
        versions = await service.get_all_versions(slug)
        
        return PromptDetailResponse(
            id=prompt.id,
            slug=prompt.slug,
            name=prompt.name,
            description=prompt.description,
            type=prompt.type,
            created_at=prompt.created_at,
            updated_at=prompt.updated_at,
            versions=[PromptVersionInfo.model_validate(v) for v in versions]
        )
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/{slug}", response_model=PromptContainerResponse)
async def update_prompt_container(
    slug: str = Path(..., description="Prompt slug"),
    data: PromptContainerUpdate = ...,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Update prompt container metadata. Admin only."""
    service = PromptService(db)
    try:
        prompt = await service.get_prompt_by_slug(slug)
        updated = await service.update_prompt(
            prompt.id,
            name=data.name,
            description=data.description
        )
        await db.commit()
        return updated
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# PROMPT VERSION endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{slug}/versions", response_model=PromptVersionResponse, status_code=201)
async def create_prompt_version(
    slug: str = Path(..., description="Prompt slug"),
    data: PromptVersionCreate = ...,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Create new version of a prompt. Admin only."""
    service = PromptService(db)
    try:
        version = await service.create_version(
            slug=slug,
            template=data.template,
            parent_version_id=data.parent_version_id,
            input_variables=data.input_variables,
            generation_config=data.generation_config
        )
        await db.commit()
        return version
    except (NotFoundException, ValidationException) as e:
        status = 404 if isinstance(e, NotFoundException) else 400
        raise HTTPException(status_code=status, detail=str(e))


@router.get("/{slug}/versions", response_model=List[PromptVersionInfo])
async def get_prompt_versions(
    slug: str = Path(..., description="Prompt slug"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get all versions of a prompt. Admin only."""
    service = PromptService(db)
    try:
        versions = await service.get_all_versions(slug)
        return [PromptVersionInfo.model_validate(v) for v in versions]
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{slug}/versions/{version}", response_model=PromptVersionResponse)
async def get_prompt_version(
    slug: str = Path(..., description="Prompt slug"),
    version: int = Path(..., description="Version number"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get specific version of a prompt. Admin only."""
    service = PromptService(db)
    try:
        version_obj = await service.get_version_by_number(slug, version)
        return version_obj
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/versions/{version_id}", response_model=PromptVersionResponse)
async def update_prompt_version(
    version_id: UUID = Path(..., description="Version ID"),
    data: PromptVersionUpdate = ...,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Update draft version. Only drafts can be edited. Admin only."""
    service = PromptService(db)
    try:
        version = await service.update_version(
            version_id=version_id,
            template=data.template,
            input_variables=data.input_variables,
            generation_config=data.generation_config
        )
        await db.commit()
        return version
    except (NotFoundException, ValidationException) as e:
        status = 404 if isinstance(e, NotFoundException) else 400
        raise HTTPException(status_code=status, detail=str(e))


@router.post("/versions/{version_id}/activate", response_model=PromptVersionResponse)
async def activate_prompt_version(
    version_id: UUID = Path(..., description="Version ID"),
    data: PromptVersionActivate = PromptVersionActivate(),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Activate a draft version. Admin only."""
    service = PromptService(db)
    try:
        version = await service.activate_version(version_id, data.archive_current)
        await db.commit()
        return version
    except (NotFoundException, ValidationException) as e:
        status = 404 if isinstance(e, NotFoundException) else 400
        raise HTTPException(status_code=status, detail=str(e))


@router.post("/versions/{version_id}/archive", response_model=PromptVersionResponse)
async def archive_prompt_version(
    version_id: UUID = Path(..., description="Version ID"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Archive a version. Admin only."""
    service = PromptService(db)
    try:
        version = await service.archive_version(version_id)
        await db.commit()
        return version
    except (NotFoundException, ValidationException) as e:
        status = 404 if isinstance(e, NotFoundException) else 400
        raise HTTPException(status_code=status, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# RENDER endpoints
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{slug}/render", response_model=PromptRenderResponse)
async def render_active_prompt(
    slug: str = Path(..., description="Prompt slug"),
    request: PromptRenderRequest = ...,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Render active version of a prompt with provided variables. Admin only."""
    service = PromptService(db)
    try:
        rendered = await service.render_active(slug, request.variables)
        return PromptRenderResponse(rendered=rendered)
    except (NotFoundException, ValidationException) as e:
        status = 404 if isinstance(e, NotFoundException) else 400
        raise HTTPException(status_code=status, detail=str(e))


@router.post("/{slug}/versions/{version}/render", response_model=PromptRenderResponse)
async def render_prompt_version(
    slug: str = Path(..., description="Prompt slug"),
    version: int = Path(..., description="Version number"),
    request: PromptRenderRequest = ...,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Render specific version of a prompt with provided variables. Admin only."""
    service = PromptService(db)
    try:
        rendered = await service.render_version(slug, version, request.variables)
        return PromptRenderResponse(rendered=rendered)
    except (NotFoundException, ValidationException) as e:
        status = 404 if isinstance(e, NotFoundException) else 400
        raise HTTPException(status_code=status, detail=str(e))
