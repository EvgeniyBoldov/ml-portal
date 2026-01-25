from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Path
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.schemas.prompts import (
    PromptCreate,
    PromptVersionCreate,
    PromptUpdate,
    PromptActivate,
    PromptResponse,
    PromptListItem,
    PromptVersionInfo,
    AgentUsingPrompt,
    PromptRenderRequest,
    PromptRenderResponse,
)
from app.services.prompt_service import PromptService
from app.core.exceptions import NotFoundException, ValidationException

router = APIRouter()


# ─────────────────────────────────────────────────────────────────────────────
# LIST & GET
# ─────────────────────────────────────────────────────────────────────────────

@router.get("", response_model=List[PromptListItem])
async def list_prompts(
    skip: int = 0,
    limit: int = 100,
    type: Optional[str] = Query(None, description="Filter by type (prompt, baseline)"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """
    List all prompts with aggregated version info. Admin only.
    """
    service = PromptService(db)
    prompts, _ = await service.list_prompts(skip=skip, limit=limit, type_filter=type)
    return prompts


@router.get("/{slug}/versions", response_model=List[PromptVersionInfo])
async def get_prompt_versions(
    slug: str = Path(..., description="Prompt slug"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """
    Get all versions of a prompt. Admin only.
    """
    service = PromptService(db)
    try:
        return await service.get_all_versions(slug)
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{slug}/versions/{version}", response_model=PromptResponse)
async def get_prompt_version(
    slug: str = Path(..., description="Prompt slug"),
    version: int = Path(..., description="Version number"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """
    Get specific version of a prompt. Admin only.
    """
    service = PromptService(db)
    try:
        return await service.get_version(slug, version)
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{slug}/agents", response_model=List[AgentUsingPrompt])
async def get_agents_using_prompt(
    slug: str = Path(..., description="Prompt slug"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """
    Get agents using this prompt. Admin only.
    """
    service = PromptService(db)
    return await service.get_agents_using_prompt(slug)


# ─────────────────────────────────────────────────────────────────────────────
# CREATE
# ─────────────────────────────────────────────────────────────────────────────

@router.post("", response_model=PromptResponse, status_code=201)
async def create_prompt(
    data: PromptCreate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """
    Create a new prompt (first version as draft). Admin only.
    """
    service = PromptService(db)
    try:
        return await service.create_prompt(data)
    except ValidationException as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{slug}/versions", response_model=PromptResponse, status_code=201)
async def create_prompt_version(
    slug: str = Path(..., description="Prompt slug"),
    data: PromptVersionCreate = ...,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """
    Create new version from existing prompt. Admin only.
    """
    service = PromptService(db)
    try:
        return await service.create_version(slug, data)
    except (NotFoundException, ValidationException) as e:
        status = 404 if isinstance(e, NotFoundException) else 400
        raise HTTPException(status_code=status, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# UPDATE
# ─────────────────────────────────────────────────────────────────────────────

@router.patch("/{prompt_id}", response_model=PromptResponse)
async def update_prompt(
    prompt_id: UUID = Path(..., description="Prompt version ID"),
    data: PromptUpdate = ...,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """
    Update a draft prompt. Only drafts can be edited. Admin only.
    """
    service = PromptService(db)
    try:
        return await service.update_draft(prompt_id, data)
    except (NotFoundException, ValidationException) as e:
        status = 404 if isinstance(e, NotFoundException) else 400
        raise HTTPException(status_code=status, detail=str(e))


@router.post("/{prompt_id}/activate", response_model=PromptResponse)
async def activate_prompt(
    prompt_id: UUID = Path(..., description="Prompt version ID"),
    data: PromptActivate = PromptActivate(),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """
    Activate a draft prompt. Optionally archive current active version. Admin only.
    """
    service = PromptService(db)
    try:
        return await service.activate(prompt_id, data.archive_current)
    except (NotFoundException, ValidationException) as e:
        status = 404 if isinstance(e, NotFoundException) else 400
        raise HTTPException(status_code=status, detail=str(e))


@router.post("/{prompt_id}/archive", response_model=PromptResponse)
async def archive_prompt(
    prompt_id: UUID = Path(..., description="Prompt version ID"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """
    Archive a prompt version. Admin only.
    """
    service = PromptService(db)
    try:
        return await service.archive(prompt_id)
    except (NotFoundException, ValidationException) as e:
        status = 404 if isinstance(e, NotFoundException) else 400
        raise HTTPException(status_code=status, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# RENDER
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/{slug}/render", response_model=PromptRenderResponse)
async def render_prompt(
    slug: str = Path(..., description="Prompt slug"),
    request: PromptRenderRequest = ...,
    version: Optional[int] = Query(None, description="Version to render (default: active)"),
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """
    Render a prompt with variables (for testing/playground). Admin only.
    """
    service = PromptService(db)
    try:
        if version:
            rendered = await service.render_version(slug, version, request.variables)
        else:
            rendered = await service.render(slug, request.variables)
        return {"rendered": rendered}
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValidationException as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/preview", response_model=PromptRenderResponse)
async def preview_template(
    template: str,
    variables: dict,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """
    Preview a template without saving it (for editor). Admin only.
    """
    service = PromptService(db)
    try:
        rendered = service._render_text(template, variables)
        return {"rendered": rendered}
    except ValidationException as e:
        raise HTTPException(status_code=400, detail=str(e))
