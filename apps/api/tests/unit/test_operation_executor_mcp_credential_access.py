from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.agents.context import RuntimeDependencies, ToolContext
from app.agents.contracts import OperationCredentialContext, ProviderExecutionTarget, ResolvedOperation
from app.agents.operation_executor import DirectOperationExecutor
from app.agents.runtime.tools import OperationExecutionFacade
from app.agents.context import ToolCall
from app.agents.runtime_graph import (
    OperationExecutionBinding,
    OperationRuntimeContext,
    RuntimeExecutionGraph,
)


@pytest.mark.asyncio
async def test_missing_credentials_fail_before_guard_admission_or_provider_dispatch():
    operation_slug = "jira.update_issue"
    target = ProviderExecutionTarget(
        operation_slug=operation_slug,
        provider_type="mcp",
        provider_instance_id=str(uuid4()),
        provider_instance_slug="jira-mcp",
        provider_url="http://jira-mcp:8080/mcp",
        data_instance_id=str(uuid4()),
        data_instance_slug="jira-prod",
        mcp_tool_name="update_issue",
        credential_policy="user_only",
    )
    binding = OperationExecutionBinding(
        operation_slug=operation_slug,
        target=target,
        context=OperationRuntimeContext(
            instance_id=str(uuid4()), instance_slug="jira-prod",
            provider_instance_id=target.provider_instance_id,
            provider_instance_slug="jira-mcp", has_credentials=False,
            credential_scope="user", config={}, provider_config={}, domain="jira",
            data_instance_url=None, provider_url=target.provider_url,
        ),
        credential=None,
    )
    guard = SimpleNamespace(admit=AsyncMock(return_value="must-not-admit"), complete=AsyncMock())
    ctx = ToolContext(user_id=uuid4(), tenant_id=uuid4(), extra={
        "runtime_execution_guard_required": True,
        "runtime_execution_guard_service": guard,
    })
    ctx.set_runtime_deps(RuntimeDependencies(
        operation_executor=DirectOperationExecutor(),
        execution_graph=RuntimeExecutionGraph(bindings={operation_slug: binding}),
    ))
    operation = ResolvedOperation(
        operation_slug=operation_slug, operation="jira.update_issue", name="Update issue",
        source="mcp", scope="system", data_instance_id=target.data_instance_id,
        data_instance_slug=target.data_instance_slug, side_effects=True, idempotent=False,
        risk_level="write", target=target,
    )

    result, _ = await OperationExecutionFacade().execute(
        ToolCall(id="call-1", tool_name=operation_slug, arguments={"key": "OPS-1"}),
        ctx, [operation],
    )

    assert result.success is False
    assert result.metadata["error_code"] == "credential_missing"
    guard.admit.assert_not_awaited()
    guard.complete.assert_not_awaited()


def test_mcp_jsonrpc_error_is_not_converted_to_an_empty_success_result():
    result = DirectOperationExecutor._mcp_tool_result_or_raise(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "error": {"code": -32000, "message": "Jira MCP request failed", "data": {"specific": "bad request"}},
        }
    )
    assert result["isError"] is True
    failure = result["_meta"]["portal.failure"]
    assert failure["kind"] == "rpc"
    assert failure["rpc_code"] == -32000
    assert failure["message"] == "Jira MCP request failed"
    assert failure["rpc_data"] == {"specific": "bad request"}


def test_mcp_response_without_result_is_not_converted_to_an_empty_success_result():
    try:
        DirectOperationExecutor._mcp_tool_result_or_raise({"jsonrpc": "2.0", "id": 2})
        raise AssertionError("Expected missing MCP result to fail the tool call")
    except ValueError as exc:
        assert str(exc) == "Invalid MCP tools/call response: missing result object"


def test_merge_mcp_args_injects_credential_access_context_when_broker_enabled():
    operation_slug = "netbox.get_device"
    target = ProviderExecutionTarget(
        operation_slug=operation_slug,
        provider_type="mcp",
        provider_instance_id=str(uuid4()),
        provider_instance_slug="netbox-mcp",
        provider_url="http://netbox-mcp:8080/mcp",
        data_instance_id=str(uuid4()),
        data_instance_slug="netbox-prod",
        mcp_tool_name="get_device",
    )

    ctx = ToolContext(
        tenant_id=uuid4(),
        user_id=uuid4(),
    )
    binding = OperationExecutionBinding(
        operation_slug=operation_slug,
        target=target,
        context=OperationRuntimeContext(
            instance_id=str(uuid4()),
            instance_slug="netbox-prod",
            provider_instance_id=str(uuid4()),
            provider_instance_slug="netbox-mcp",
            has_credentials=True,
            credential_scope="auto",
            config={"base_path": "/api/dcim"},
            provider_config={},
            domain="netbox",
            data_instance_url=None,
            provider_url=target.provider_url,
        ),
        credential=OperationCredentialContext(
            auth_type="token",
            payload={"token": "raw-secret"},
            credential_id=str(uuid4()),
            owner_type="user",
        ),
    )
    deps = RuntimeDependencies(
        execution_graph=RuntimeExecutionGraph(bindings={operation_slug: binding}),
    )
    ctx.set_runtime_deps(deps)

    executor = DirectOperationExecutor()
    executor._mcp_credential_broker_enabled = True

    binding, _ = executor._resolve_target_binding(operation_slug, ctx)
    merged = executor._merge_mcp_args(target, {"name": "sw01"}, ctx, binding=binding)
    instance_ctx = merged.get("instance_context") or {}
    assert "credential_access" in instance_ctx
    assert "credentials" not in instance_ctx
    assert instance_ctx["credential_access"].get("token")
    assert instance_ctx["credential_access"].get("resolve_url")
    assert "raw-secret" not in str(merged)


@pytest.mark.asyncio
async def test_merge_mcp_args_rejects_raw_credentials_when_broker_required(caplog):
    operation_slug = "netbox.get_device"
    target = ProviderExecutionTarget(
        operation_slug=operation_slug,
        provider_type="mcp",
        provider_instance_id=str(uuid4()),
        provider_instance_slug="netbox-mcp",
        provider_url="http://netbox-mcp:8080/mcp",
        data_instance_id=str(uuid4()),
        data_instance_slug="netbox-prod",
        mcp_tool_name="get_device",
    )
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4())
    binding = OperationExecutionBinding(
        operation_slug=operation_slug,
        target=target,
        context=OperationRuntimeContext(
            instance_id=str(uuid4()),
            instance_slug="netbox-prod",
            provider_instance_id=str(uuid4()),
            provider_instance_slug="netbox-mcp",
            has_credentials=True,
            credential_scope="auto",
            config={},
            provider_config={},
            domain="netbox",
            data_instance_url=None,
            provider_url=target.provider_url,
        ),
        credential=OperationCredentialContext(
            auth_type="token",
            payload={"token": "raw-secret"},
            credential_id=None,
            owner_type="user",
        ),
    )
    deps = RuntimeDependencies(execution_graph=RuntimeExecutionGraph(bindings={operation_slug: binding}))
    ctx.set_runtime_deps(deps)

    executor = DirectOperationExecutor()
    executor._mcp_credential_broker_enabled = True
    executor._mcp_credential_broker_required = True
    executor._mcp_allow_raw_credential_fallback = False

    binding, _ = executor._resolve_target_binding(operation_slug, ctx)
    try:
        executor._merge_mcp_args(target, {"name": "sw01"}, ctx, binding=binding)
        raise AssertionError("Expected broker-required guard to reject raw credential fallback")
    except ValueError as exc:
        assert str(exc) == (
            "MCP credential_access could not be issued and raw credential fallback is disabled"
        )

    result = await executor.execute(
        ToolCall(id="call-broker-required", tool_name=operation_slug, arguments={"name": "sw01"}),
        ctx,
    )
    assert result.success is False
    assert "stage=credential_argument_build" in caplog.text
    assert "failure_reason=broker_access_not_issued" in caplog.text


def test_merge_mcp_args_allows_raw_credentials_when_fallback_enabled():
    operation_slug = "netbox.get_device"
    target = ProviderExecutionTarget(
        operation_slug=operation_slug,
        provider_type="mcp",
        provider_instance_id=str(uuid4()),
        provider_instance_slug="netbox-mcp",
        provider_url="http://netbox-mcp:8080/mcp",
        data_instance_id=str(uuid4()),
        data_instance_slug="netbox-prod",
        mcp_tool_name="get_device",
    )
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4())
    binding = OperationExecutionBinding(
        operation_slug=operation_slug,
        target=target,
        context=OperationRuntimeContext(
            instance_id=str(uuid4()),
            instance_slug="netbox-prod",
            provider_instance_id=str(uuid4()),
            provider_instance_slug="netbox-mcp",
            has_credentials=True,
            credential_scope="auto",
            config={},
            provider_config={},
            domain="netbox",
            data_instance_url=None,
            provider_url=target.provider_url,
        ),
        credential=OperationCredentialContext(
            auth_type="token",
            payload={"token": "raw-secret"},
            credential_id=None,
            owner_type="user",
        ),
    )
    deps = RuntimeDependencies(execution_graph=RuntimeExecutionGraph(bindings={operation_slug: binding}))
    ctx.set_runtime_deps(deps)

    executor = DirectOperationExecutor()
    executor._mcp_credential_broker_enabled = True
    executor._mcp_credential_broker_required = True
    executor._mcp_allow_raw_credential_fallback = True

    binding, _ = executor._resolve_target_binding(operation_slug, ctx)
    merged = executor._merge_mcp_args(target, {"name": "sw01"}, ctx, binding=binding)
    instance_ctx = merged.get("instance_context") or {}
    assert instance_ctx.get("credentials", {}).get("token") == "raw-secret"


def test_merge_mcp_args_requires_and_preserves_bound_collection_slug():
    operation_slug = "instance.docs.collection.document.search"
    target = ProviderExecutionTarget(
        operation_slug=operation_slug,
        provider_type="mcp",
        provider_instance_id=str(uuid4()),
        provider_instance_slug="docs-mcp",
        provider_url="http://docs-mcp:8080/mcp",
        data_instance_id=str(uuid4()),
        data_instance_slug="docs",
        mcp_tool_name="document_search",
        credential_policy="not_required",
    )
    collection_id = str(uuid4())
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4())
    binding = OperationExecutionBinding(
        operation_slug=operation_slug,
        target=target,
        context=OperationRuntimeContext(
            instance_id=str(uuid4()),
            instance_slug="docs",
            scope="collection",
            collection_id=collection_id,
            collection_slug="reglament",
            provider_instance_id=str(uuid4()),
            provider_instance_slug="docs-mcp",
            has_credentials=False,
            credential_scope="auto",
            config={},
            provider_config={},
            domain="collection.document",
            data_instance_url=None,
            provider_url=target.provider_url,
        ),
        credential=None,
    )
    deps = RuntimeDependencies(execution_graph=RuntimeExecutionGraph(bindings={operation_slug: binding}))
    ctx.set_runtime_deps(deps)

    executor = DirectOperationExecutor()
    binding, _ = executor._resolve_target_binding(operation_slug, ctx)
    merged = executor._merge_mcp_args(
        target,
        {"collection_slug": "reglament", "query": "nginx"},
        ctx,
        binding=binding,
    )

    assert merged["collection_slug"] == "reglament"
    assert "collection_id" not in merged


def test_mcp_adapter_legacy_diagnostic_is_normalized_and_preserved():
    result = DirectOperationExecutor._mcp_tool_result_or_raise({'error': {
        'code': -32000, 'message': 'MCP adapter request failed', 'data': {
            'stage': 'upstream_request', 'error_type': 'UnicodeEncodeError',
            'request_id': 'call-1', 'payload': 'private', 'detail': 'diagnostic detail',
        },
    }})
    assert result["isError"] is True
    failure = result["_meta"]["portal.failure"]
    assert failure["kind"] == "rpc"
    assert failure["details"]["stage"] == "upstream_request"
    assert failure["details"]["error_type"] == "UnicodeEncodeError"
    assert failure["details"]["request_id"] == "call-1"
    assert failure["details"]["payload"] == "private"
    assert failure["details"]["detail"] == "diagnostic detail"
