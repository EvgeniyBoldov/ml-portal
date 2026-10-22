from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import db_session, require_admin
from app.api.v1.routers.admin import orchestration as orchestration_router


@pytest.mark.asyncio
async def test_orchestration_settings_http_reads_and_updates_executor_fields(monkeypatch):
    now = datetime.now(timezone.utc)
    settings = SimpleNamespace(
        id=uuid4(), executor_model="llm.default", executor_temperature=0.4,
        tool_use_guard=None, retry_instruction=None, intent_messages=None,
        prompt_budgets=None, prompt_labels=None, created_at=now, updated_at=now,
    )
    service = SimpleNamespace(
        get=AsyncMock(return_value=settings),
        update_executor=AsyncMock(return_value=settings),
    )
    monkeypatch.setattr(orchestration_router, "OrchestrationService", lambda _db: service)
    session = AsyncMock()
    app = FastAPI()
    app.include_router(orchestration_router.router, prefix="/orchestration")
    app.dependency_overrides[db_session] = lambda: session
    app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=str(uuid4()))

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        read = await client.get("/orchestration")
        update = await client.patch("/orchestration/executor", json={
            "executor_model": "llm.primary", "executor_temperature": 0.7,
            "tool_use_guard": "Only use configured tools.",
        })

    assert read.status_code == 200
    assert read.json()["executor_model"] == "llm.default"
    assert update.status_code == 200
    service.update_executor.assert_awaited_once_with({
        "executor_model": "llm.primary", "executor_temperature": 0.7,
        "tool_use_guard": "Only use configured tools.",
    })
    assert session.commit.await_count == 2
