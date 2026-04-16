"""
Platform Settings Admin API — global platform configuration (singleton).

Stores global policy text, safety gates, and platform caps.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.services.platform_settings_service import PlatformSettingsService
from app.schemas.platform_settings import PlatformSettingsResponse, PlatformSettingsUpdate

router = APIRouter()


# ─── Endpoints ────────────────────────────────────────────────────────

@router.get("", response_model=PlatformSettingsResponse)
async def get_platform_settings(
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Get platform settings."""
    service = PlatformSettingsService(db)
    settings = await service.get()
    await db.commit()
    return PlatformSettingsResponse.model_validate(settings)


@router.patch("", response_model=PlatformSettingsResponse)
async def update_platform_settings(
    data: PlatformSettingsUpdate,
    db: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
):
    """Update platform settings."""
    service = PlatformSettingsService(db)
    
    # Build kwargs from non-None fields
    kwargs = {}
    update_data = data.model_dump(exclude_unset=True, exclude_none=True)
    
    if update_data:
        settings = await service.update(**update_data)
    else:
        settings = await service.get()

    await db.commit()
    return PlatformSettingsResponse.model_validate(settings)
