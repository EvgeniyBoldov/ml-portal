from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.api.v1.routers.admin import system_llm_roles as roles_router
from app.schemas.system_llm_roles import SystemLLMRoleCreate, SystemLLMRoleUpdate


def _router_dependencies(monkeypatch, service):
    monkeypatch.setattr(roles_router, "SystemLLMRoleService", lambda _session: service)
    monkeypatch.setattr(roles_router, "_serialize_role", lambda role: role)


@pytest.mark.asyncio
async def test_role_mutations_commit_their_transaction(monkeypatch):
    created_role = SimpleNamespace(name="created")
    updated_role = SimpleNamespace(name="updated")
    activated_role = SimpleNamespace(name="activated")
    service = SimpleNamespace(
        create_role=AsyncMock(return_value=created_role),
        update_role=AsyncMock(return_value=updated_role),
        delete_role=AsyncMock(return_value=True),
        activate_role=AsyncMock(return_value=activated_role),
    )
    _router_dependencies(monkeypatch, service)
    user = SimpleNamespace()

    create_session = AsyncMock()
    assert await roles_router.create_role(
        SystemLLMRoleCreate(role_type="memory"), create_session, user
    ) is created_role
    create_session.commit.assert_awaited_once()

    update_session = AsyncMock()
    assert await roles_router.update_role(
        uuid4(), SystemLLMRoleUpdate(mission="updated"), update_session, user
    ) is updated_role
    update_session.commit.assert_awaited_once()

    delete_session = AsyncMock()
    assert await roles_router.delete_role(uuid4(), delete_session, user) == {
        "message": "Role deleted successfully"
    }
    delete_session.commit.assert_awaited_once()

    activate_session = AsyncMock()
    assert await roles_router.activate_role(uuid4(), activate_session, user) is activated_role
    activate_session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_memory_role_update_commits_before_return(monkeypatch):
    role = SimpleNamespace(name="memory")
    service = SimpleNamespace(update_active_role=AsyncMock(return_value=role))
    _router_dependencies(monkeypatch, service)
    session = AsyncMock()

    result = await roles_router.update_active_role(
        "memory", SystemLLMRoleUpdate(identity="memory preparation"), session, SimpleNamespace()
    )

    assert result is role
    service.update_active_role.assert_awaited_once()
    session.commit.assert_awaited_once()
