from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.permission_service import EffectivePermissions, PermissionService


def test_effective_permissions_helpers():
    perms = EffectivePermissions(
        tool_permissions={"tool.a": True, "tool.b": False},
        collection_permissions={"docs": True, "tickets": False},
        default_tool_allow=False,
        default_collection_allow=False,
    )

    assert perms.allowed_tools == ["tool.a"]
    assert perms.allowed_collections == ["docs"]
    assert perms.is_tool_allowed("tool.a") is True
    assert perms.is_tool_allowed("tool.b") is False
    assert perms.is_tool_allowed("tool.unknown") is False
    assert perms.is_collection_allowed("docs") is True
    assert perms.is_collection_allowed("tickets") is False


@pytest.mark.asyncio
async def test_permission_service_resolve_permissions_from_legacy_sets():
    service = PermissionService(session=AsyncMock())

    default_set = type(
        "PS",
        (),
        {
            "scope": "default",
            "tool_permissions": {"tool.search": "allowed", "tool.delete": "denied"},
            "collection_permissions": {"docs": "allowed", "secrets": "denied"},
        },
    )()
    tenant_set = type(
        "PS",
        (),
        {
            "scope": "tenant",
            "tool_permissions": {"tool.delete": "allowed"},
            "collection_permissions": {"docs": "denied"},
        },
    )()
    user_set = type(
        "PS",
        (),
        {
            "scope": "user",
            "tool_permissions": {"tool.delete": "denied"},
            "collection_permissions": {"docs": "allowed"},
        },
    )()

    service.repo.get_all_for_context = AsyncMock(return_value=[default_set, tenant_set, user_set])
    service._apply_rbac_rules = AsyncMock()

    perms = await service.resolve_permissions()

    assert perms.is_tool_allowed("tool.search") is True
    assert perms.is_tool_allowed("tool.delete") is False
    assert perms.is_collection_allowed("docs") is True
    assert perms.is_collection_allowed("secrets") is False
    service._apply_rbac_rules.assert_awaited_once()

