"""Admin-only dashboard and a deliberately narrow period contract."""
from unittest.mock import AsyncMock
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import db_session, require_admin, get_current_user
from app.api.v1.routers.admin.dashboard import router
from app.schemas.dashboard import DashboardResponse, UsageSummary


@pytest.mark.asyncio
async def test_dashboard_requires_authentication():
    app = FastAPI()
    app.include_router(router, prefix="/admin/dashboard")
    app.dependency_overrides[db_session] = lambda: AsyncMock()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/admin/dashboard?days=7")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_numeric_query_period_is_parsed_and_other_periods_are_rejected(monkeypatch):
    app = FastAPI()
    app.include_router(router, prefix="/admin/dashboard")
    app.dependency_overrides[db_session] = lambda: AsyncMock()
    app.dependency_overrides[require_admin] = lambda: object()
    calls = []

    async def overview(_self, days):
        calls.append(days)
        now = datetime.now(timezone.utc)
        return DashboardResponse(days=days, generated_at=now, period_start=now,
            coverage_started_at=now, current=UsageSummary(), previous=UsageSummary(),
            timeline=[], models=[], agents=[], collections=[], memory_scopes=[],
            memory_available=True, problems=[])

    monkeypatch.setattr("app.services.dashboard_service.DashboardService.overview", overview)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        for days in (1, 7, 30):
            response = await client.get(f"/admin/dashboard?days={days}")
            assert response.status_code == 200 and response.json()["days"] == days
        assert (await client.get("/admin/dashboard?days=2")).status_code == 422
    assert calls == [1, 7, 30]


@pytest.mark.asyncio
async def test_dashboard_rejects_nonadmin_user():
    app = FastAPI()
    app.include_router(router, prefix="/admin/dashboard")
    app.dependency_overrides[db_session] = lambda: AsyncMock()
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(is_admin=False, role="reader")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/admin/dashboard")).status_code == 403
