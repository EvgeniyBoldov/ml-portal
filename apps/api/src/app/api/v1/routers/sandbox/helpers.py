"""Shared helpers for sandbox sub-routers."""
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import UserCtx
from app.models.user import Users
from app.models.tenant import Tenants
from app.services.sandbox_service import SandboxService


def user_uuid(user: UserCtx) -> uuid.UUID:
    return uuid.UUID(user.id)


async def tenant_uuid(db: AsyncSession, user: UserCtx) -> uuid.UUID:
    if user.tenant_ids:
        return uuid.UUID(user.tenant_ids[0])

    result = await db.execute(
        select(Tenants.id)
        .where(Tenants.is_active.is_(True))
        .order_by(Tenants.created_at.asc())
        .limit(1)
    )
    tenant_id = result.scalar_one_or_none()
    if tenant_id:
        return tenant_id

    raise HTTPException(
        status_code=400,
        detail="No tenant available for sandbox session",
    )


async def get_owner_email(db: AsyncSession, owner_id: uuid.UUID) -> str:
    result = await db.execute(select(Users.email).where(Users.id == owner_id))
    row = result.scalar_one_or_none()
    return row or "unknown"


async def check_session_owner(
    svc: SandboxService, session_id: uuid.UUID, user: UserCtx
) -> None:
    """Raise 403 if user is not the session owner."""
    if not await svc.is_owner(session_id, user_uuid(user)):
        raise HTTPException(
            status_code=403,
            detail="Only session owner can modify this sandbox session",
        )
