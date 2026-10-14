from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import db_session
from app.api.mcp import router as router_module
import importlib
from app.core.security import create_access_token

module = importlib.import_module("app.api.mcp.router")


@pytest.fixture
def mcp(monkeypatch):
    app = FastAPI()
    app.include_router(router_module, prefix="/api/v1")
    session = AsyncMock()
    app.dependency_overrides[db_session] = lambda: session
    user_id, tenant_id = uuid4(), uuid4()
    token = create_access_token(str(user_id), "mcp@example.test", "reader", [], [])
    monkeypatch.setattr(module, "resolve_active_user_tenant_ids", AsyncMock(return_value=[tenant_id]))
    ping = AsyncMock(return_value={})
    monkeypatch.setattr(module, "MCPHandlers", lambda *_: SimpleNamespace(handle_ping=ping))
    @asynccontextmanager
    async def log_request(**kwargs):
        yield SimpleNamespace(set_response=lambda response: None)
    monkeypatch.setattr(module, "MCPAuditService", lambda _: SimpleNamespace(log_request=log_request))
    return SimpleNamespace(app=app, token=token, ping=ping)


@pytest.mark.asyncio
async def test_mcp_uses_standard_bearer_auth(mcp):
    async with httpx.AsyncClient(app=mcp.app, base_url="http://test") as client:
        response = await client.post("/api/v1/mcp", headers={"Authorization": f"Bearer {mcp.token}"},
            json={"jsonrpc": "2.0", "id": 1, "method": "ping"})
    assert response.status_code == 200
    assert response.json()["result"] == {}
    mcp.ping.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("headers", [{}, {"X-API-Key": "legacy"}, {"Authorization": "Bearer legacy"}])
async def test_mcp_rejects_missing_or_legacy_authentication(mcp, headers):
    async with httpx.AsyncClient(app=mcp.app, base_url="http://test") as client:
        response = await client.post("/api/v1/mcp", headers=headers,
            json={"jsonrpc": "2.0", "id": 1, "method": "initialize"})
    assert response.status_code == 401
    mcp.ping.assert_not_awaited()
