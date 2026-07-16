from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.permission_service import PermissionService


@pytest.mark.asyncio
async def test_permission_resolution_uses_configurable_default_fallbacks():
    service = PermissionService(session=AsyncMock())
    service.rule_repo.list_platform_rules = AsyncMock(return_value=[])
    service.rule_repo.list_by_tenant = AsyncMock(return_value=[])
    service.rule_repo.list_by_user = AsyncMock(return_value=[])

    effective = await service.resolve_permissions(
        default_collection_allow=False,
    )

    assert effective.is_collection_allowed("tickets") is False


@pytest.mark.asyncio
async def test_permission_resolution_defaults_to_deny_when_no_rules_are_present():
    service = PermissionService(session=AsyncMock())
    service.rule_repo.list_platform_rules = AsyncMock(return_value=[])
    service.rule_repo.list_by_tenant = AsyncMock(return_value=[])
    service.rule_repo.list_by_user = AsyncMock(return_value=[])

    effective = await service.resolve_permissions()

    assert effective.is_collection_allowed("tickets") is False
