from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.agents.context import OperationCall, RuntimeDependencies, ToolContext, ToolResult
from app.agents.contracts import ProviderExecutionTarget, ResolvedOperation
from app.agents.runtime.confirmation import ConfirmationService, build_operation_fingerprint
from app.agents.runtime.tools import ConfirmationRequiredError, OperationExecutor


def _operation(*, requires_confirmation: bool = True) -> ResolvedOperation:
    target = ProviderExecutionTarget(
        operation_slug="instance.netbox.delete_device",
        provider_type="mcp",
        provider_instance_id=str(uuid4()),
        provider_instance_slug="netbox-mcp",
        provider_url="http://netbox-mcp:8080/mcp",
        data_instance_id=str(uuid4()),
        data_instance_slug="netbox-prod",
        mcp_tool_name="delete_device",
    )
    return ResolvedOperation(
        operation_slug=target.operation_slug,
        operation="netbox.delete_device",
        name="Delete device",
        description="Delete Netbox device",
        input_schema={"type": "object", "required": ["id"]},
        data_instance_id=target.data_instance_id,
        data_instance_slug=target.data_instance_slug,
        source="mcp",
        requires_confirmation=requires_confirmation,
        risk_level="destructive",
        side_effects=True,
        target=target,
    )


def _context(*, confirmation_tokens: list[str]):
    ctx = ToolContext(
        tenant_id=uuid4(),
        user_id=uuid4(),
        chat_id=uuid4(),
        extra={"confirmation_tokens": confirmation_tokens},
    )
    runtime_executor = AsyncMock(return_value=ToolResult.ok({"ok": True}))
    deps = RuntimeDependencies(operation_executor=SimpleNamespace(execute=runtime_executor))
    ctx.set_runtime_deps(deps)
    return ctx, runtime_executor


def _sandbox_context(*, confirmed_fingerprints: list[str]):
    ctx = ToolContext(
        tenant_id=uuid4(),
        user_id=uuid4(),
        chat_id=None,
        extra={"sandbox_confirmed_fingerprints": confirmed_fingerprints},
    )
    runtime_executor = AsyncMock(return_value=ToolResult.ok({"ok": True}))
    deps = RuntimeDependencies(operation_executor=SimpleNamespace(execute=runtime_executor))
    ctx.set_runtime_deps(deps)
    return ctx, runtime_executor


@pytest.mark.asyncio
async def test_confirmation_gate_blocks_without_token_and_allows_with_token_then_rejects_foreign():
    executor = OperationExecutor()
    operation = _operation()
    args = {"id": "dev-1"}
    call = OperationCall(id="call-1", operation_slug=operation.operation_slug, arguments=args)

    # No token -> blocked and provider executor must not be called.
    ctx, runtime_executor = _context(confirmation_tokens=[])
    with pytest.raises(ConfirmationRequiredError):
        await executor.execute(call, ctx, [operation])
    runtime_executor.assert_not_awaited()

    # Valid token for this user/chat/fingerprint -> allowed.
    fingerprint = build_operation_fingerprint(
        tool_slug=operation.operation_slug,
        operation=operation.operation,
        args=args,
    )
    token, _ = ConfirmationService().issue(
        user_id=ctx.user_id,
        chat_id=ctx.chat_id,  # type: ignore[arg-type]
        fingerprint=fingerprint,
    )
    ctx.extra["confirmation_tokens"] = [token]
    result, _ = await executor.execute(call, ctx, [operation])
    assert result.success is True
    runtime_executor.assert_awaited_once()

    # Token from another user -> blocked again.
    foreign_token, _ = ConfirmationService().issue(
        user_id=uuid4(),
        chat_id=ctx.chat_id,  # type: ignore[arg-type]
        fingerprint=fingerprint,
    )
    ctx_foreign, runtime_executor_foreign = _context(confirmation_tokens=[foreign_token])
    with pytest.raises(ConfirmationRequiredError):
        await executor.execute(call, ctx_foreign, [operation])
    runtime_executor_foreign.assert_not_awaited()


@pytest.mark.asyncio
async def test_confirmation_gate_blocks_in_sandbox_without_preapproval_and_allows_with_fingerprint():
    executor = OperationExecutor()
    operation = _operation()
    args = {"id": "dev-2"}
    call = OperationCall(id="call-2", operation_slug=operation.operation_slug, arguments=args)
    fingerprint = build_operation_fingerprint(
        tool_slug=operation.operation_slug,
        operation=operation.operation,
        args=args,
    )

    ctx_blocked, runtime_executor_blocked = _sandbox_context(confirmed_fingerprints=[])
    with pytest.raises(ConfirmationRequiredError):
        await executor.execute(call, ctx_blocked, [operation])
    runtime_executor_blocked.assert_not_awaited()

    ctx_allowed, runtime_executor_allowed = _sandbox_context(
        confirmed_fingerprints=[fingerprint]
    )
    result, _ = await executor.execute(call, ctx_allowed, [operation])
    assert result.success is True
    runtime_executor_allowed.assert_awaited_once()
