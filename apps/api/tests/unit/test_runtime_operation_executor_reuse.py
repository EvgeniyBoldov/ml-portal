from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.agents.context import RuntimeDependencies, ToolCall, ToolContext, ToolResult
from app.agents.contracts import ProviderExecutionTarget, ResolvedOperation
from app.agents.runtime.tools import ToolExecutor
from app.runtime.memory.tool_ledger import ToolLedger


def _operation() -> ResolvedOperation:
    target = ProviderExecutionTarget(
        operation_slug="collection.sql.execute",
        provider_type="mcp",
        provider_instance_id=str(uuid4()),
        provider_instance_slug="sql-mcp",
        provider_url="http://sql-mcp:8080/mcp",
        data_instance_id=str(uuid4()),
        data_instance_slug="sql-demo",
        mcp_tool_name="execute_sql",
        timeout_s=20,
    )
    return ResolvedOperation(
        operation_slug="collection.sql.execute",
        operation="collection.sql.execute",
        name="SQL Execute",
        description="Execute SQL",
        input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
        data_instance_id=target.data_instance_id,
        data_instance_slug=target.data_instance_slug,
        provider_instance_id=target.provider_instance_id,
        provider_instance_slug=target.provider_instance_slug,
        source="mcp",
        target=target,
    )


def _record_success(ledger: ToolLedger, operation: ResolvedOperation, call_id: str,
                    arguments: dict, *, execution_id: str = "execution-a",
                    target_identity: str | None = None) -> None:
    ledger.register_call(operation=operation.operation_slug, call_id=call_id,
        arguments=arguments, iteration=1, agent_slug="agent", phase_id="task-a")
    ledger.set_call_target(call_id=call_id,
        target_identity=target_identity or ":".join(str(value or "") for value in (
            operation.operation_slug, operation.target.provider_instance_id,
            operation.target.data_instance_id, operation.target.provider_url,
            operation.target.mcp_tool_name)), arguments=arguments, execution_id=execution_id)
    ledger.register_result(call_id=call_id, success=True, data={"rows": [{"v": 1}]})


def test_argument_normalization_applies_schema_defaults_before_reuse_keying():
    operation = _operation().model_copy(update={"input_schema": {
        "type": "object", "properties": {"limit": {"type": "integer", "default": 20}},
    }})
    assert ToolExecutor._normalize_args(operation, {}) == {"limit": 20}


@pytest.mark.asyncio
async def test_operation_executor_reuses_from_tool_ledger():
    operation = _operation()
    call = ToolCall(
        id="call-2",
        tool_name="collection.sql.execute",
        arguments={"query": "select 1", "collection_slug": "sql-demo"},
    )
    ledger = ToolLedger()
    _record_success(ledger, operation, "call-1", call.arguments)
    ledger.entries[-1].sources = [{"url": "https://example.test/result"}]

    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4())
    deps = RuntimeDependencies(operation_executor=AsyncMock())
    ctx.set_runtime_deps(deps)
    ctx.extra["runtime_tool_ledger"] = ledger
    ctx.extra["runtime_tool_reuse_enabled"] = True
    ctx.extra["lifecycle_agent_execution_id"] = "execution-a"

    executor = ToolExecutor()
    result, sources = await executor.execute(
        operation_call=call,
        ctx=ctx,
        operations=[operation],
    )

    assert result.success is True
    assert result.metadata.get("reused") is True
    assert result.metadata.get("reused_from_call_id") == "call-1"
    assert result.data == {"rows": [{"v": 1}]}
    assert sources == [{"url": "https://example.test/result"}]
    deps.operation_executor.execute.assert_not_called()


@pytest.mark.asyncio
async def test_operation_executor_reuses_identical_call_when_fresh_retrieval_is_required():
    operation = _operation()
    arguments = {"query": "select 1", "collection_slug": "sql-demo"}
    call = ToolCall(id="call-2", tool_name=operation.operation_slug, arguments=arguments)
    ledger = ToolLedger()
    _record_success(ledger, operation, "call-1", arguments)
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4())
    deps = RuntimeDependencies(operation_executor=AsyncMock())
    deps.operation_executor.execute.return_value = ToolResult.ok({"rows": [{"v": 2}]})
    ctx.set_runtime_deps(deps)
    ctx.extra.update({
        "runtime_tool_ledger": ledger,
        "lifecycle_agent_execution_id": "execution-a",
        "task_freshness_policy": "require_retrieval",
    })

    result, _ = await ToolExecutor().execute(operation_call=call, ctx=ctx, operations=[operation])

    assert result.metadata.get("reused") is True
    assert result.metadata.get("reused_from_call_id") == "call-1"
    assert result.data == {"rows": [{"v": 1}]}
    deps.operation_executor.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_reused_confirmable_operation_does_not_consume_a_new_confirmation():
    operation = _operation().model_copy(update={"requires_confirmation": True})
    arguments = {"query": "select 1", "collection_slug": "sql-demo"}
    ledger = ToolLedger()
    _record_success(ledger, operation, "call-1", arguments)
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4())
    ctx.set_runtime_deps(RuntimeDependencies(operation_executor=AsyncMock()))
    ctx.extra["runtime_tool_ledger"] = ledger
    ctx.extra["lifecycle_agent_execution_id"] = "execution-a"

    result, _ = await ToolExecutor().execute(
        operation_call=ToolCall(id="call-2", tool_name=operation.operation_slug, arguments=arguments),
        ctx=ctx,
        operations=[operation],
    )

    assert result.metadata.get("reused") is True


@pytest.mark.asyncio
async def test_facade_dispatches_first_call_then_reuses_successful_repeat_even_when_cache_disabled():
    operation = _operation()
    arguments = {"query": "select 1", "collection_slug": "sql-demo"}
    ledger = ToolLedger()
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4())
    deps = RuntimeDependencies(operation_executor=AsyncMock())
    deps.operation_executor.execute.return_value = ToolResult.ok({"rows": [{"v": 1}]})
    ctx.set_runtime_deps(deps)
    ctx.extra.update(runtime_execution_tool_ledger=ledger, runtime_agent_execution_id="execution-a")

    first, _ = await ToolExecutor().execute(
        operation_call=ToolCall(id="call-1", tool_name=operation.operation_slug, arguments=arguments),
        ctx=ctx, operations=[operation])
    assert first.success
    deps.operation_executor.execute.assert_awaited_once()
    ledger.register_result(call_id="call-1", success=True, data={"rows": [{"v": 1}]})
    ctx.extra["runtime_tool_reuse_enabled"] = False

    second, _ = await ToolExecutor().execute(
        operation_call=ToolCall(id="call-2", tool_name=operation.operation_slug, arguments=arguments),
        ctx=ctx, operations=[operation])
    assert second.metadata.get("reused") is True
    assert second.data == {"rows": [{"v": 1}]}
    deps.operation_executor.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_facade_reuse_is_scoped_by_execution_and_resolved_target():
    operation = _operation()
    arguments = {"query": "select 1", "collection_slug": "sql-demo"}
    ledger = ToolLedger()
    _record_success(ledger, operation, "call-1", arguments, execution_id="execution-a")
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4())
    deps = RuntimeDependencies(operation_executor=AsyncMock())
    deps.operation_executor.execute.return_value = ToolResult.ok({"fresh": True})
    ctx.set_runtime_deps(deps)
    ctx.extra.update(runtime_execution_tool_ledger=ledger, runtime_agent_execution_id="execution-b")
    result, _ = await ToolExecutor().execute(
        operation_call=ToolCall(id="call-2", tool_name=operation.operation_slug, arguments=arguments),
        ctx=ctx, operations=[operation])
    assert not result.metadata.get("reused")
    deps.operation_executor.execute.assert_awaited_once()
    ledger.register_result(call_id="call-2", success=True, data={"fresh": True})

    _record_success(ledger, operation, "call-3", arguments,
                    execution_id="execution-b", target_identity="different-target")
    other_target_operation = _operation()
    result, _ = await ToolExecutor().execute(
        operation_call=ToolCall(id="call-4", tool_name=other_target_operation.operation_slug, arguments=arguments),
        ctx=ctx, operations=[other_target_operation])
    assert not result.metadata.get("reused")
    assert deps.operation_executor.execute.await_count == 2


@pytest.mark.asyncio
async def test_facade_does_not_block_the_current_pending_call():
    operation = _operation()
    arguments = {"query": "select 1", "collection_slug": "sql-demo"}
    ledger = ToolLedger()
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4())
    deps = RuntimeDependencies(operation_executor=AsyncMock())
    deps.operation_executor.execute.return_value = ToolResult.ok({"ok": True})
    ctx.set_runtime_deps(deps)
    ctx.extra.update(runtime_tool_ledger=ledger, lifecycle_agent_execution_id="execution-a")
    ledger.register_call(operation=operation.operation_slug, call_id="call-1", arguments=arguments,
                         iteration=1, agent_slug="agent", phase_id="task-a")

    result, _ = await ToolExecutor().execute(
        operation_call=ToolCall(id="call-1", tool_name=operation.operation_slug, arguments=arguments),
        ctx=ctx, operations=[operation])
    assert result.success
    deps.operation_executor.execute.assert_awaited_once()
