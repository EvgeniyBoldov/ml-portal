from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.permission_service import PermissionService


def _perm(
    *,
    scope: str,
    instance_permissions=None,
    agent_permissions=None,
    collection_permissions=None,
):
    return SimpleNamespace(
        scope=scope,
        instance_permissions=instance_permissions or {},
        agent_permissions=agent_permissions or {},
        collection_permissions=collection_permissions or {},
    )


@pytest.mark.asyncio
async def test_permission_resolution_applies_user_tenant_default_precedence_for_collections():
    service = PermissionService(session=AsyncMock())
    service.repo.get_all_for_context = AsyncMock(
        return_value=[
            _perm(
                scope="default",
                collection_permissions={
                    "tickets": "allowed",
                    "contracts": "denied",
                },
            ),
            _perm(
                scope="tenant",
                collection_permissions={
                    "tickets": "undefined",
                    "contracts": "allowed",
                },
            ),
            _perm(
                scope="user",
                collection_permissions={"contracts": "denied"},
            ),
        ]
    )
    service._apply_rbac_rules = AsyncMock(return_value=None)

    effective = await service.resolve_permissions()

    # tenant undefined -> default allowed
    assert effective.collection_permissions["tickets"] is True
    # user denied overrides tenant allowed
    assert effective.collection_permissions["contracts"] is False


@pytest.mark.asyncio
async def test_permission_resolution_uses_configurable_default_fallbacks():
    service = PermissionService(session=AsyncMock())
    service.repo.get_all_for_context = AsyncMock(return_value=[])
    service._apply_rbac_rules = AsyncMock(return_value=None)

    effective = await service.resolve_permissions(
        default_collection_allow=False,
    )

    assert effective.is_collection_allowed("tickets") is False


@pytest.mark.asyncio
async def test_permission_resolution_defaults_to_deny_when_no_rules_are_present():
    service = PermissionService(session=AsyncMock())
    service.repo.get_all_for_context = AsyncMock(return_value=[])
    service._apply_rbac_rules = AsyncMock(return_value=None)

    effective = await service.resolve_permissions()

    assert effective.is_collection_allowed("tickets") is False
