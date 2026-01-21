from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
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
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """
    List all prompts (latest versions) with agents using them. Admin only.
    """
    service = PromptService(db)
    prompts, _ = await service.list_prompts(skip=skip, limit=limit, type_filter=type)
    
    # Enrich with agent information
    result = []
    for prompt in prompts:
        agents = await service.get_agents_using_prompt(prompt.slug)
        prompt_dict = prompt.__dict__.copy()
        prompt_dict['used_by_agents'] = agents
        result.append(PromptResponse(**prompt_dict))
    
    return result


@router.post("", response_model=PromptResponse)
async def create_prompt(
    prompt_in: PromptCreate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """
    Create a new prompt or new version of existing prompt. Admin only.
    """
    service = PromptService(db)
    try:
        return await service.create_or_update(
            slug=prompt_in.slug,
            name=prompt_in.name,
            template=prompt_in.template,
            description=prompt_in.description,
            input_variables=prompt_in.input_variables,
            generation_config=prompt_in.generation_config,
            type=prompt_in.type
        )
    except ValidationException as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{slug}", response_model=PromptResponse)
async def get_prompt(
    slug: str,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """
    Get prompt by slug. Admin only.
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
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """
    Render a prompt with variables (for testing/playground). Admin only.
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
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """
    Preview a template without saving it (for editor). Admin only.
    """
    service = PromptService(db)
    try:
        rendered = service._render_text(request.template, variables)
        return {"rendered": rendered}
    except ValidationException as e:
        raise HTTPException(status_code=400, detail=str(e))
