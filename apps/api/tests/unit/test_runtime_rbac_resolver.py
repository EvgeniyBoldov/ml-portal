from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.agents.runtime_rbac_resolver import RuntimeRbacResolver
from app.core.config import get_settings
from app.services.permission_service import EffectivePermissions


@pytest.mark.asyncio
async def test_runtime_rbac_resolver_uses_passed_defaults_when_test_mode_disabled(monkeypatch):
    monkeypatch.setenv("RUNTIME_RBAC_ENFORCE_RULES", "false")
    monkeypatch.setenv("RUNTIME_RBAC_ALLOW_UNDEFINED", "false")
    get_settings.cache_clear()

    resolver = RuntimeRbacResolver(permission_service=SimpleNamespace(resolve_permissions=AsyncMock()))
    effective = await resolver.resolve_effective_permissions(
        user_id=uuid4(),
        tenant_id=uuid4(),
        default_collection_allow=True,
    )

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
        default_collection_allow=False,
    )

    assert effective.default_collection_allow is True
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_runtime_rbac_resolver_calls_permission_service_when_enforced(monkeypatch):
    monkeypatch.setenv("RUNTIME_RBAC_ENFORCE_RULES", "true")
    monkeypatch.setenv("RUNTIME_RBAC_ALLOW_UNDEFINED", "true")
    get_settings.cache_clear()

    expected = SimpleNamespace(default_collection_allow=True)
    permission_service = SimpleNamespace(resolve_permissions=AsyncMock(return_value=expected))
    resolver = RuntimeRbacResolver(permission_service=permission_service)

    result = await resolver.resolve_effective_permissions(
        user_id=uuid4(),
        tenant_id=uuid4(),
        default_collection_allow=False,
    )

    assert result is expected
    permission_service.resolve_permissions.assert_awaited_once()
    call = permission_service.resolve_permissions.await_args
    assert call.kwargs["default_collection_allow"] is True
    get_settings.cache_clear()


def test_runtime_rbac_resolver_filter_agents_by_slug_respects_explicit_rules(monkeypatch):
    monkeypatch.setenv("RUNTIME_RBAC_ENFORCE_RULES", "true")
    monkeypatch.setenv("RUNTIME_RBAC_ALLOW_UNDEFINED", "false")
    get_settings.cache_clear()

    resolver = RuntimeRbacResolver(permission_service=SimpleNamespace(resolve_permissions=AsyncMock()))
    perms = EffectivePermissions(agent_permissions={"allowed-agent": True, "denied-agent": False})
    agents = [
        SimpleNamespace(slug="allowed-agent"),
        SimpleNamespace(slug="denied-agent"),
        SimpleNamespace(slug="undefined-agent"),
    ]

    filtered, denied = resolver.filter_agents_by_slug(
        agents,
        effective_permissions=perms,
        slug_getter=lambda item: item.slug,
        default_allow=True,
    )

    assert [a.slug for a in filtered] == ["allowed-agent", "undefined-agent"]
    assert denied == ["denied-agent"]
    get_settings.cache_clear()


def test_runtime_rbac_resolver_checks_collection_permissions():
    resolver = RuntimeRbacResolver(permission_service=SimpleNamespace(resolve_permissions=AsyncMock()))
    perms = EffectivePermissions(
        collection_permissions={"collection.allowed": True, "collection.denied": False},
        default_collection_allow=False,
    )

    assert resolver.is_collection_allowed(perms, "collection.allowed") is True
    assert resolver.is_collection_allowed(perms, "collection.denied") is False
