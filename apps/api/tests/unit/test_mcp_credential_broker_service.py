from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import UnauthorizedError
from app.services.credential_service import DecryptedCredentials
from app.services.mcp_credential_broker_service import MCPCredentialBrokerService


@pytest.mark.asyncio
async def test_mcp_credential_broker_issue_and_resolve_roundtrip():
    user_id = uuid4()
    tenant_id = uuid4()
    provider_instance_id = uuid4()
    credential_id = uuid4()

    access_ctx = MCPCredentialBrokerService.issue_access_context(
        user_id=user_id,
        tenant_id=tenant_id,
        provider_instance_id=str(provider_instance_id),
        provider_instance_slug="netbox-mcp",
        data_instance_id=str(uuid4()),
        data_instance_slug="netbox-prod",
        operation_slug="netbox.get_device",
        mcp_tool_name="get_device",
        credential_id=str(credential_id),
        auth_type="token",
        owner_type="user",
    )

    svc = MCPCredentialBrokerService(session=SimpleNamespace())
    svc.credential_service.get_credentials = AsyncMock(
        return_value=SimpleNamespace(
            id=credential_id,
            instance_id=provider_instance_id,
            owner_user_id=user_id,
            owner_tenant_id=None,
            owner_platform=False,
        )
    )
    svc.credential_service.get_decrypted_credentials = AsyncMock(
        return_value=DecryptedCredentials(
            auth_type="token",
            payload={"token": "secret-token"},
            credential_id=credential_id,
            owner_type="user",
        )
    )

    resolved = await svc.resolve_access_token(access_ctx.token)
    assert resolved.credential_id == credential_id
    assert resolved.instance_id == provider_instance_id
    assert resolved.auth_type == "token"
    assert resolved.payload["token"] == "secret-token"


@pytest.mark.asyncio
async def test_mcp_credential_broker_rejects_owner_mismatch():
    user_id = uuid4()
    tenant_id = uuid4()
    provider_instance_id = uuid4()
    credential_id = uuid4()

    access_ctx = MCPCredentialBrokerService.issue_access_context(
        user_id=user_id,
        tenant_id=tenant_id,
        provider_instance_id=str(provider_instance_id),
        provider_instance_slug="netbox-mcp",
        data_instance_id=str(uuid4()),
        data_instance_slug="netbox-prod",
        operation_slug="netbox.get_device",
        mcp_tool_name="get_device",
        credential_id=str(credential_id),
        auth_type="token",
        owner_type="user",
    )

    svc = MCPCredentialBrokerService(session=SimpleNamespace())
    svc.credential_service.get_credentials = AsyncMock(
        return_value=SimpleNamespace(
            id=credential_id,
            instance_id=provider_instance_id,
            owner_user_id=uuid4(),  # different user -> must fail
            owner_tenant_id=None,
            owner_platform=False,
        )
    )
    svc.credential_service.get_decrypted_credentials = AsyncMock(
        return_value=DecryptedCredentials(
            auth_type="token",
            payload={"token": "secret-token"},
            credential_id=credential_id,
            owner_type="user",
        )
    )

    with pytest.raises(UnauthorizedError, match="owner mismatch"):
        await svc.resolve_access_token(access_ctx.token)
