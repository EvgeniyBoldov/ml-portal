"""
Platform Settings Admin API — global platform configuration (singleton).

Stores default policy, limit, and RBAC policy for the entire platform.
"""
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from datetime import datetime

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.services.platform_settings_service import PlatformSettingsService

router = APIRouter()


# ─── Schemas ──────────────────────────────────────────────────────────

class PlatformSettingsResponse(BaseModel):
    id: UUID
    default_policy_id: Optional[UUID]
    default_limit_id: Optional[UUID]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class PlatformSettingsUpdate(BaseModel):
    default_policy_id: Optional[UUID] = None
    default_limit_id: Optional[UUID] = None


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

    kwargs = {}
    if data.default_policy_id is not None:
        kwargs["default_policy_id"] = data.default_policy_id
    if data.default_limit_id is not None:
        kwargs["default_limit_id"] = data.default_limit_id

    if not kwargs:
        settings = await service.get()
    else:
        settings = await service.update(**kwargs)

    await db.commit()
    return PlatformSettingsResponse.model_validate(settings)
