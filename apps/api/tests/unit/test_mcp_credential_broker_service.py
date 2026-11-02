from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.core.exceptions import UnauthorizedError
from app.services.credential_service import DecryptedCredentials
from app.services.mcp_credential_broker_service import MCPCredentialBrokerService


@pytest.mark.asyncio
@pytest.mark.parametrize("credential_source", ["data", "provider", "unrelated"])
async def test_mcp_broker_accepts_only_bound_data_credentials(
    credential_source: str,
):
    user_id, tenant_id = uuid4(), uuid4()
    provider_id, data_id, unrelated_id, credential_id = uuid4(), uuid4(), uuid4(), uuid4()
    instance_id = {"data": data_id, "provider": provider_id, "unrelated": unrelated_id}[
        credential_source
    ]
    access = MCPCredentialBrokerService.issue_access_context(
        user_id=user_id,
        tenant_id=tenant_id,
        provider_instance_id=str(provider_id),
        provider_instance_slug="ml-mcp",
        data_instance_id=str(data_id),
        data_instance_slug="ml",
        operation_slug="model.predict",
        mcp_tool_name="model.predict",
        credential_id=str(credential_id),
        auth_type="token",
        owner_type="platform",
    )
    svc = MCPCredentialBrokerService(session=SimpleNamespace())
    svc.credential_service.get_credentials = AsyncMock(return_value=SimpleNamespace(
        id=credential_id, instance_id=instance_id,
        owner_platform=True, owner_user_id=None, owner_tenant_id=None, is_active=True,
    ))
    svc.credential_service.get_decrypted_credentials = AsyncMock(return_value=DecryptedCredentials(
        auth_type="token", payload={"token": "predict-secret"},
        credential_id=credential_id, owner_type="platform",
    ))

    if credential_source != "data":
        with pytest.raises(UnauthorizedError, match="does not belong"):
            await svc.resolve_access_token(access.token)
        svc.credential_service.get_decrypted_credentials.assert_not_awaited()
    else:
        resolved = await svc.resolve_access_token(access.token)
        assert resolved.instance_id == instance_id
        assert resolved.payload == {"token": "predict-secret"}


@pytest.mark.asyncio
async def test_mcp_credential_broker_issue_and_resolve_roundtrip():
    user_id = uuid4()
    tenant_id = uuid4()
    provider_instance_id = uuid4()
    data_instance_id = uuid4()
    credential_id = uuid4()

    access_ctx = MCPCredentialBrokerService.issue_access_context(
        user_id=user_id,
        tenant_id=tenant_id,
        provider_instance_id=str(provider_instance_id),
        provider_instance_slug="netbox-mcp",
        data_instance_id=str(data_instance_id),
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
            instance_id=data_instance_id,
            is_active=True,
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
    assert resolved.instance_id == data_instance_id
    assert resolved.auth_type == "token"
    assert resolved.payload["token"] == "secret-token"


@pytest.mark.asyncio
async def test_mcp_credential_broker_rejects_owner_mismatch():
    user_id = uuid4()
    tenant_id = uuid4()
    provider_instance_id = uuid4()
    data_instance_id = uuid4()
    credential_id = uuid4()

    access_ctx = MCPCredentialBrokerService.issue_access_context(
        user_id=user_id,
        tenant_id=tenant_id,
        provider_instance_id=str(provider_instance_id),
        provider_instance_slug="netbox-mcp",
        data_instance_id=str(data_instance_id),
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
            instance_id=data_instance_id,
            is_active=True,
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


@pytest.mark.asyncio
async def test_mcp_broker_rejects_revoked_credential_before_decryption():
    data_id, credential_id = uuid4(), uuid4()
    access = MCPCredentialBrokerService.issue_access_context(
        user_id=uuid4(), tenant_id=uuid4(), provider_instance_id=str(uuid4()),
        provider_instance_slug="mcp", data_instance_id=str(data_id), data_instance_slug="data",
        operation_slug="read", mcp_tool_name="read", credential_id=str(credential_id),
        auth_type="token", owner_type="platform",
    )
    svc = MCPCredentialBrokerService(session=SimpleNamespace())
    svc.credential_service.get_credentials = AsyncMock(return_value=SimpleNamespace(
        id=credential_id, instance_id=data_id, is_active=False, owner_platform=True,
    ))
    svc.credential_service.get_decrypted_credentials = AsyncMock()
    with pytest.raises(UnauthorizedError, match="inactive"):
        await svc.resolve_access_token(access.token)
    svc.credential_service.get_decrypted_credentials.assert_not_awaited()
