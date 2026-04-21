from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.agents.credential_resolver import CredentialsUnavailableError, RuntimeCredentialResolver
from app.models.tool_instance import ToolInstance


def _remote_instance() -> ToolInstance:
    return ToolInstance(
        id=uuid4(),
        slug="netbox-data",
        name="Netbox Data",
        description="Remote netbox",
        instance_kind="data",
        placement="remote",
        domain="netbox",
        url="http://example.test",
        config={},
        is_active=True,
    )


@pytest.mark.asyncio
async def test_destructive_auto_with_only_platform_credentials_raises_unavailable():
    service = SimpleNamespace(
        resolve_credentials=AsyncMock(return_value=None),
        resolve_credential_reference=AsyncMock(return_value=None),
    )
    resolver = RuntimeCredentialResolver(service, mcp_credential_broker_enabled=False)

    with pytest.raises(CredentialsUnavailableError):
        await resolver.resolve_for_execution(
            _remote_instance(),
            user_id=uuid4(),
            tenant_id=uuid4(),
            tool_slug="instance.netbox-data.netbox.delete",
            operation="netbox.delete",
            credential_scope="auto",
            risk_level="destructive",
            side_effects=True,
        )


@pytest.mark.asyncio
async def test_safe_auto_uses_platform_first_and_succeeds_with_platform_credentials():
    service = SimpleNamespace(
        resolve_credentials=AsyncMock(
            return_value=SimpleNamespace(
                auth_type="token",
                payload={"token": "platform-token"},
                credential_id=uuid4(),
                owner_type="platform",
            )
        ),
        resolve_credential_reference=AsyncMock(return_value=None),
    )
    resolver = RuntimeCredentialResolver(service, mcp_credential_broker_enabled=False)

    context = await resolver.resolve_for_execution(
        _remote_instance(),
        user_id=uuid4(),
        tenant_id=uuid4(),
        tool_slug="instance.netbox-data.netbox.get",
        operation="netbox.get",
        credential_scope="auto",
        risk_level="safe",
        side_effects=False,
    )
    assert context is not None
    call = service.resolve_credentials.await_args
    assert call.kwargs["strategy"] == "PLATFORM_FIRST"


@pytest.mark.asyncio
async def test_write_auto_requires_user_credentials_and_does_not_use_platform_strategy():
    service = SimpleNamespace(
        resolve_credentials=AsyncMock(
            return_value=SimpleNamespace(
                auth_type="token",
                payload={"token": "user-token"},
                credential_id=uuid4(),
                owner_type="user",
            )
        ),
        resolve_credential_reference=AsyncMock(return_value=None),
    )
    resolver = RuntimeCredentialResolver(service, mcp_credential_broker_enabled=False)

    context = await resolver.resolve_for_execution(
        _remote_instance(),
        user_id=uuid4(),
        tenant_id=uuid4(),
        tool_slug="instance.netbox-data.netbox.update",
        operation="netbox.update",
        credential_scope="auto",
        risk_level="write",
        side_effects=True,
    )
    assert context is not None
    call = service.resolve_credentials.await_args
    assert call.kwargs["strategy"] == "USER_ONLY"
