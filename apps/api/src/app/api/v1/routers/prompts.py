from typing import Any, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db, get_current_user
from app.models.user import Users
from app.schemas.prompts import (
    PromptCreate, 
    PromptResponse, 
    PromptRenderRequest, 
    PromptRenderResponse
)
from app.services.prompt_service import PromptService
from app.core.exceptions import NotFoundException, ValidationException

router = APIRouter()


@router.get("", response_model=List[PromptResponse])
async def list_prompts(
    skip: int = 0,
    limit: int = 100,
    type: str = Query(None, description="Filter by type (chat, agent, task)"),
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    """
    List all prompts (latest versions).
    """
    service = PromptService(db)
    prompts, _ = await service.list_prompts(skip=skip, limit=limit, type_filter=type)
    return prompts


@router.post("", response_model=PromptResponse)
async def create_prompt(
    prompt_in: PromptCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    """
    Create a new prompt or new version of existing prompt.
    """
    # TODO: Add RBAC check (only MLOps/Admin)
    service = PromptService(db)
    try:
        return await service.create_or_update(
            slug=prompt_in.slug,
            name=prompt_in.name,
            template=prompt_in.template,
            description=prompt_in.description,
            input_variables=prompt_in.input_variables,
            model_config=prompt_in.model_config,
            type=prompt_in.type
        )
    except ValidationException as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{slug}", response_model=PromptResponse)
async def get_prompt(
    slug: str,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    """
    Get prompt by slug.
    """
    service = PromptService(db)
    try:
        return await service.get_template(slug)
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{slug}/render", response_model=PromptRenderResponse)
async def render_prompt(
    slug: str,
    request: PromptRenderRequest,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    """
    Render a prompt with variables (for testing/playground).
    """
    service = PromptService(db)
    try:
        rendered = await service.render(slug, request.variables)
        return {"rendered": rendered}
    except NotFoundException as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValidationException as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/preview", response_model=PromptRenderResponse)
async def preview_prompt_template(
    request: PromptCreate,
    variables: dict,
    db: AsyncSession = Depends(get_db),
    current_user: Users = Depends(get_current_user),
):
    """
    Preview a template without saving it (for editor).
    """
    service = PromptService(db)
    try:
        rendered = service._render_text(request.template, variables)
        return {"rendered": rendered}
    except ValidationException as e:
        raise HTTPException(status_code=400, detail=str(e))
