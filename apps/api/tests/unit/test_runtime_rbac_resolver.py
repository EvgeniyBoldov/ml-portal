from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.agents.runtime_rbac_resolver import RuntimeRbacResolver
from app.core.config import get_settings


@pytest.mark.asyncio
async def test_runtime_rbac_resolver_uses_passed_defaults_when_test_mode_disabled(monkeypatch):
    monkeypatch.setenv("RUNTIME_RBAC_ENFORCE_RULES", "false")
    monkeypatch.setenv("RUNTIME_RBAC_ALLOW_UNDEFINED", "false")
    get_settings.cache_clear()

    resolver = RuntimeRbacResolver(permission_service=SimpleNamespace(resolve_permissions=AsyncMock()))
    effective = await resolver.resolve_effective_permissions(
        user_id=uuid4(),
        tenant_id=uuid4(),
        default_tool_allow=False,
        default_collection_allow=True,
    )

    assert effective.default_tool_allow is False
    assert effective.default_collection_allow is True
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_runtime_rbac_resolver_overrides_defaults_in_allow_undefined_mode(monkeypatch):
    monkeypatch.setenv("RUNTIME_RBAC_ENFORCE_RULES", "false")
    monkeypatch.setenv("RUNTIME_RBAC_ALLOW_UNDEFINED", "true")
    get_settings.cache_clear()

    resolver = RuntimeRbacResolver(permission_service=SimpleNamespace(resolve_permissions=AsyncMock()))
    effective = await resolver.resolve_effective_permissions(
        user_id=uuid4(),
        tenant_id=uuid4(),
        default_tool_allow=False,
        default_collection_allow=False,
    )

    assert effective.default_tool_allow is True
    assert effective.default_collection_allow is True
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_runtime_rbac_resolver_calls_permission_service_when_enforced(monkeypatch):
    monkeypatch.setenv("RUNTIME_RBAC_ENFORCE_RULES", "true")
    monkeypatch.setenv("RUNTIME_RBAC_ALLOW_UNDEFINED", "true")
    get_settings.cache_clear()

    expected = SimpleNamespace(default_tool_allow=True, default_collection_allow=True)
    permission_service = SimpleNamespace(resolve_permissions=AsyncMock(return_value=expected))
    resolver = RuntimeRbacResolver(permission_service=permission_service)

    result = await resolver.resolve_effective_permissions(
        user_id=uuid4(),
        tenant_id=uuid4(),
        default_tool_allow=False,
        default_collection_allow=False,
    )

    assert result is expected
    permission_service.resolve_permissions.assert_awaited_once()
    call = permission_service.resolve_permissions.await_args
    assert call.kwargs["default_tool_allow"] is True
    assert call.kwargs["default_collection_allow"] is True
    get_settings.cache_clear()
