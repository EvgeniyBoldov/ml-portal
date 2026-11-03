from __future__ import annotations

import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.agents.context import ToolContext
from app.agents.contracts import OperationCredentialContext, ProviderExecutionTarget
from app.agents.credential_resolver import RuntimeCredentialResolver
from app.agents.operation_executor import DirectOperationExecutor
from app.repositories.credential_set_repository import CredentialRepository


@pytest.mark.asyncio
@pytest.mark.parametrize("broker_enabled", [True, False])
async def test_resolution_metadata_is_visible_in_console_without_secrets(caplog, broker_enabled):
    credential_id = uuid4()
    credential = SimpleNamespace(
        credential_id=credential_id, auth_type="token", owner_type="user",
        payload={"token": "credential-secret-never-log"},
    )
    service = SimpleNamespace(
        resolve_credentials=AsyncMock(return_value=credential),
        resolve_credential_reference=AsyncMock(return_value=credential),
    )
    resolver = RuntimeCredentialResolver(service, mcp_credential_broker_enabled=broker_enabled)
    instance = SimpleNamespace(id=uuid4(), slug="jira", is_local=False)
    with caplog.at_level(logging.INFO):
        result = await resolver.resolve_for_execution(
            instance, user_id=uuid4(), tenant_id=uuid4(), operation="jira.get_issue",
        )
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert result.credential_id == str(credential_id)
    assert str(credential_id) in messages
    assert '"credential_strategy": "USER_FIRST"' in messages
    assert '"credential_auth_type": "token"' in messages
    assert "credential-secret-never-log" not in messages


@pytest.mark.parametrize("enabled, credential_id, reason", [
    (False, "known-credential", "broker_disabled"),
    (True, None, "credential_id_missing"),
])
def test_delivery_failure_logs_exact_reason_without_payload(caplog, enabled, credential_id, reason):
    executor = DirectOperationExecutor()
    executor._mcp_credential_broker_enabled = enabled
    credential = OperationCredentialContext(
        credential_id=credential_id, auth_type="token", owner_type="user",
        payload={"token": "credential-secret-never-log"},
    )
    target = ProviderExecutionTarget(
        operation_slug="collection.jira.get_issue", provider_type="mcp",
        data_instance_id=str(uuid4()), data_instance_slug="jira",
        provider_instance_id=str(uuid4()), provider_instance_slug="mcp-jira",
        mcp_tool_name="get_issue", credential_policy="user_tenant_platform",
    )
    ctx = ToolContext(user_id=uuid4(), tenant_id=uuid4(), extra={
        "run_id": "diagnostic-run", "runtime_active_tool_call_id": "diagnostic-call",
    })
    with caplog.at_level(logging.INFO):
        result = executor._build_mcp_credential_access_context(
            target=target, credential_context=credential, ctx=ctx,
        )
    assert result is None
    assert f"reason={reason}" in caplog.text
    assert "run_id=diagnostic-run call_id=diagnostic-call" in caplog.text
    assert "expected_delivery=credential_access" in caplog.text
    assert "credential-secret-never-log" not in caplog.text


@pytest.mark.asyncio
async def test_scope_fallback_logs_rejected_scope_and_selected_credential(caplog):
    repo = CredentialRepository(SimpleNamespace())
    credential = SimpleNamespace(id=uuid4(), auth_type="basic", encrypted_payload="encrypted-secret")
    repo._find_user = AsyncMock(return_value=None)
    repo._find_tenant = AsyncMock(return_value=credential)
    repo._find_platform = AsyncMock()
    with caplog.at_level(logging.INFO):
        result = await repo.resolve_for_instance(
            uuid4(), strategy="USER_FIRST", user_id=uuid4(), tenant_id=uuid4(),
        )
    assert result is credential
    assert "scope=user" in caplog.text
    assert "reason=no_active_credential_for_instance_and_owner" in caplog.text
    assert f"scope=tenant credential_id={credential.id} auth_type=basic reason=selected" in caplog.text
    assert "encrypted-secret" not in caplog.text
    repo._find_platform.assert_not_awaited()


def test_delivery_policy_logs_configured_and_effective_flags(caplog, monkeypatch):
    monkeypatch.setenv("ENV", "production")
    from app.core.config import Settings
    from app.agents import operation_executor

    settings = Settings.model_construct(
        ENV="production", MCP_CREDENTIAL_BROKER_ENABLED=False,
        MCP_CREDENTIAL_BROKER_REQUIRED=False, MCP_ALLOW_RAW_CREDENTIAL_FALLBACK=True,
        MCP_CREDENTIAL_BROKER_BASE_URL="https://user:never-log-secret@broker.test/private",
    )
    monkeypatch.setattr(operation_executor, "get_settings", lambda: settings)
    with caplog.at_level(logging.INFO):
        executor = DirectOperationExecutor()
    assert executor._mcp_credential_broker_enabled is True
    assert executor._mcp_credential_broker_required is True
    assert executor._mcp_allow_raw_credential_fallback is False
    assert "configured_broker_enabled=False" in caplog.text
    assert "effective_broker_enabled=True" in caplog.text
    assert "broker_base_url_present=True" in caplog.text
    assert "never-log-secret" not in caplog.text
    assert "broker.test" not in caplog.text
