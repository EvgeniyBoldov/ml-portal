"""Platform dashboard; the endpoint never starts probes or indexing jobs."""
from enum import IntEnum

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import db_session, require_admin
from app.core.security import UserCtx
from app.schemas.dashboard import DashboardResponse
from app.services.dashboard_service import DashboardService

router = APIRouter()


class DashboardPeriod(IntEnum):
    DAY = 1
    WEEK = 7
    MONTH = 30


@router.get("", response_model=DashboardResponse)
async def dashboard(
    days: DashboardPeriod = Query(DashboardPeriod.WEEK),
    session: AsyncSession = Depends(db_session),
    _: UserCtx = Depends(require_admin),
) -> DashboardResponse:
    return await DashboardService(session).overview(days.value)
