from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.agents.context import OperationCall, RuntimeDependencies, ToolContext
from app.agents.contracts import ProviderExecutionTarget, ResolvedOperation
from app.agents.runtime.tools import OperationExecutor
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


@pytest.mark.asyncio
async def test_operation_executor_reuses_from_tool_ledger():
    operation = _operation()
    call = OperationCall(
        id="call-2",
        operation_slug="collection.sql.execute",
        arguments={"query": "select 1"},
    )
    ledger = ToolLedger()
    ledger.register_call(
        operation="collection.sql.execute",
        call_id="call-1",
        arguments={"query": "select 1"},
        iteration=1,
        agent_slug="mon.net",
        phase_id=None,
    )
    ledger.register_result(call_id="call-1", success=True, data={"rows": [{"v": 1}]})

    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4())
    deps = RuntimeDependencies(operation_executor=AsyncMock())
    ctx.set_runtime_deps(deps)
    ctx.extra["runtime_tool_ledger"] = ledger
    ctx.extra["runtime_tool_reuse_enabled"] = True

    executor = OperationExecutor()
    result, sources = await executor.execute(
        operation_call=call,
        ctx=ctx,
        operations=[operation],
    )

    assert result.success is True
    assert result.metadata.get("reused") is True
    assert result.metadata.get("reused_from_call_id") == "call-1"
    assert result.data == {"rows": [{"v": 1}]}
    assert sources == []
    deps.operation_executor.execute.assert_not_called()

