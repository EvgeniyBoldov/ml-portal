from __future__ import annotations

from uuid import uuid4

from app.agents.context import RuntimeDependencies, ToolContext
from app.agents.contracts import OperationCredentialContext, ProviderExecutionTarget
from app.agents.operation_executor import DirectOperationExecutor
from app.agents.runtime_graph import (
    OperationExecutionBinding,
    OperationRuntimeContext,
    RuntimeExecutionGraph,
)


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


def test_merge_mcp_args_rejects_raw_credentials_when_broker_required():
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
        assert "broker is required" in str(exc).lower()


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
