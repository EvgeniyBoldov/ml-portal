"""
Orchestration router - global executor settings.

Router/Planner models are configured via SystemLLMRole.
Caps/gates are configured via PlatformSettings.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.schemas.orchestration import (
    OrchestrationSettingsResponse,
    ExecutorSettingsUpdate,
)
from app.services.orchestration_service import OrchestrationService

router = APIRouter(prefix="", tags=["orchestration"])


@router.get("", response_model=OrchestrationSettingsResponse)
async def get_orchestration_settings(
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get orchestration settings."""
    service = OrchestrationService(db)
    settings = await service.get()
    await db.commit()
    return OrchestrationSettingsResponse.model_validate(settings)


@router.patch("/executor", response_model=OrchestrationSettingsResponse)
async def update_executor_settings(
    data: ExecutorSettingsUpdate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Update executor settings."""
    service = OrchestrationService(db)
    settings = await service.update_executor(data.model_dump(exclude_unset=True))
    await db.commit()
    return OrchestrationSettingsResponse.model_validate(settings)
