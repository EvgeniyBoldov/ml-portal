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
        slug="remote-instance",
        name="Remote Instance",
        description="Remote",
        instance_kind="data",
        placement="remote",
        domain="netbox",
        url="http://example.test",
        config={},
        is_active=True,
    )


def _local_instance() -> ToolInstance:
    return ToolInstance(
        id=uuid4(),
        slug="local-instance",
        name="Local Instance",
        description="Local",
        instance_kind="data",
        placement="local",
        domain="collection.table",
        url="",
        config={},
        is_active=True,
    )


@pytest.mark.asyncio
async def test_runtime_credential_resolver_uses_explicit_scope_strategy_without_broker():
    service = SimpleNamespace(
        resolve_credentials=AsyncMock(
            return_value=SimpleNamespace(
                auth_type="token",
                payload={"token": "platform-token"},
                credential_id=uuid4(),
                owner_type="platform",
            )
        )
    )
    resolver = RuntimeCredentialResolver(service, mcp_credential_broker_enabled=False)

    context = await resolver.resolve_for_execution(
        _remote_instance(),
        user_id=uuid4(),
        tenant_id=uuid4(),
        credential_scope="user",
    )

    assert context is not None
    service.resolve_credentials.assert_awaited_once()
    call = service.resolve_credentials.await_args
    assert call.kwargs["strategy"] == "USER_ONLY"


@pytest.mark.asyncio
async def test_runtime_credential_resolver_uses_explicit_scope_with_broker():
    cred_id = uuid4()
    service = SimpleNamespace(
        resolve_credential_reference=AsyncMock(
            return_value=SimpleNamespace(
                auth_type="token",
                credential_id=cred_id,
                owner_type="platform",
            )
        ),
        get_decrypted_credentials=AsyncMock(
            return_value=SimpleNamespace(payload={"username": "demo", "password": "secret"})
        ),
    )
    resolver = RuntimeCredentialResolver(service, mcp_credential_broker_enabled=True)

    context = await resolver.resolve_for_execution(
        _remote_instance(),
        user_id=uuid4(),
        tenant_id=uuid4(),
        credential_scope="platform",
    )

    assert context is not None
    assert context.payload == {"username": "demo", "password": "secret"}
    assert context.owner_type == "platform"
    service.resolve_credential_reference.assert_awaited_once()
    service.get_decrypted_credentials.assert_awaited_once_with(cred_id)
    call = service.resolve_credential_reference.await_args
    assert call.kwargs["strategy"] == "PLATFORM_ONLY"


@pytest.mark.asyncio
async def test_runtime_credential_resolver_skips_local_instance():
    service = SimpleNamespace(
        resolve_credentials=AsyncMock(),
        resolve_credential_reference=AsyncMock(),
    )
    resolver = RuntimeCredentialResolver(service, mcp_credential_broker_enabled=False)

    context = await resolver.resolve_for_execution(
        _local_instance(),
        user_id=uuid4(),
        tenant_id=uuid4(),
        credential_scope="auto",
    )

    assert context is None
    service.resolve_credentials.assert_not_awaited()


@pytest.mark.asyncio
async def test_runtime_credential_resolver_raises_for_strict_missing_credentials():
    service = SimpleNamespace(
        resolve_credentials=AsyncMock(return_value=None),
        resolve_credential_reference=AsyncMock(return_value=None),
    )
    resolver = RuntimeCredentialResolver(service, mcp_credential_broker_enabled=False)

    with pytest.raises(CredentialsUnavailableError, match="requires user credentials"):
        await resolver.resolve_for_execution(
            _remote_instance(),
            user_id=uuid4(),
            tenant_id=uuid4(),
            tool_slug="instance.netbox.delete",
            operation="netbox.delete",
            credential_scope="user",
            risk_level="destructive",
            side_effects=True,
        )
