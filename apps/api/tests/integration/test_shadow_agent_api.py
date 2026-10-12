"""HTTP authentication and identity propagation for the shadow entry point."""
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import db_session, get_llm_client
from app.api.v1.routers import shadow_agents as module
from app.core.exceptions import ForbiddenError, ExternalServiceError, install_exception_handlers
from app.core.security import create_access_token, create_refresh_token
from app.schemas.shadow_agents import ShadowAgentResponse


@pytest.fixture
def api(monkeypatch):
    app = FastAPI()
    app.include_router(module.router, prefix="/api/v1")
    install_exception_handlers(app)
    session = AsyncMock()
    app.dependency_overrides[db_session] = lambda: session
    app.dependency_overrides[get_llm_client] = lambda: AsyncMock()
    user_id, tenant_id = uuid4(), uuid4()
    memberships = AsyncMock(return_value=[tenant_id])
    monkeypatch.setattr(module, "resolve_active_user_tenant_ids", memberships)
    invoke = AsyncMock(return_value=ShadowAgentResponse(agent="shadow-a", result={"ok": True}))
    monkeypatch.setattr(module, "ShadowAgentService", lambda *_: SimpleNamespace(invoke=invoke))
    token = create_access_token(str(user_id), "shadow-test@example.test", "reader", [str(uuid4())], ["invoke"])
    return SimpleNamespace(app=app, session=session, invoke=invoke, token=token,
                           user_id=user_id, tenant_id=tenant_id, memberships=memberships)


@pytest.mark.asyncio
async def test_bearer_invocation_uses_token_user_and_current_membership(api):
    async with httpx.AsyncClient(app=api.app, base_url="http://test") as client:
        response = await client.post("/api/v1/agents/shadow/invoke", headers={"Authorization": f"Bearer {api.token}"},
                                     json={"agent": "shadow-a", "data": {"text": "hello"}})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"
    assert response.json() == {"agent": "shadow-a", "result": {"ok": True}}
    kwargs = api.invoke.call_args.kwargs
    assert kwargs["user_id"] == api.user_id
    assert kwargs["tenant_id"] == api.tenant_id
    assert kwargs["scopes"] == ["invoke"]
    assert kwargs["request_id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("auth", ["missing", "cookie", "invalid", "refresh"])
async def test_missing_cookie_invalid_and_refresh_credentials_are_rejected(api, auth):
    headers = {}
    cookies = {}
    if auth == "cookie":
        cookies["access_token"] = api.token
    elif auth == "invalid":
        headers["Authorization"] = "Bearer invalid"
    elif auth == "refresh":
        headers["Authorization"] = f"Bearer {create_refresh_token(str(api.user_id))}"
    async with httpx.AsyncClient(app=api.app, base_url="http://test", cookies=cookies) as client:
        response = await client.post("/api/v1/agents/shadow/invoke", headers=headers,
                                     json={"agent": "shadow-a", "data": {}})
    assert response.status_code == 401
    api.invoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_user_cannot_supply_execution_identity(api):
    async with httpx.AsyncClient(app=api.app, base_url="http://test") as client:
        response = await client.post("/api/v1/agents/shadow/invoke", headers={"Authorization": f"Bearer {api.token}"},
                                     json={"agent": "shadow-a", "data": {}, "user_id": str(uuid4())})
    assert response.status_code == 422
    api.invoke.assert_not_awaited()


@pytest.mark.asyncio
async def test_missing_membership_prevents_execution(api):
    api.memberships.return_value = []
    async with httpx.AsyncClient(app=api.app, base_url="http://test") as client:
        response = await client.post("/api/v1/agents/shadow/invoke", headers={"Authorization": f"Bearer {api.token}"},
                                     json={"agent": "shadow-a", "data": {}})
    assert response.status_code == 403
    api.invoke.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("error,status", [(ForbiddenError("denied"), 403), (ExternalServiceError("invalid result"), 502)])
async def test_domain_failures_are_json_http_errors(api, error, status):
    api.invoke.side_effect = error
    async with httpx.AsyncClient(app=api.app, base_url="http://test") as client:
        response = await client.post("/api/v1/agents/shadow/invoke", headers={"Authorization": f"Bearer {api.token}"},
                                     json={"agent": "shadow-a", "data": {}})
    assert response.status_code == status
    assert response.headers["content-type"] == "application/problem+json"
    assert isinstance(response.json(), dict)
