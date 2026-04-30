from __future__ import annotations

from unittest.mock import AsyncMock
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.agents.context import OperationCall, RuntimeDependencies, ToolContext, ToolResult
from app.agents.contracts import ProviderExecutionTarget, ResolvedOperation
from app.agents.runtime.tools import OperationExecutor, _JSONSCHEMA_AVAILABLE
from app.runtime.operation_errors import RuntimeErrorCode


def _operation(*, schema: dict) -> ResolvedOperation:
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
        input_schema=schema,
        data_instance_id=target.data_instance_id,
        data_instance_slug=target.data_instance_slug,
        provider_instance_id=target.provider_instance_id,
        provider_instance_slug=target.provider_instance_slug,
        source="mcp",
        target=target,
    )


def _ctx() -> ToolContext:
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4())
    deps = RuntimeDependencies(
        operation_executor=SimpleNamespace(
            execute=AsyncMock(return_value=ToolResult.ok({"ok": True}))
        )
    )
    ctx.set_runtime_deps(deps)
    return ctx


@pytest.mark.asyncio
async def test_operation_executor_rejects_nested_type_mismatch():
    operation = _operation(
        schema={
            "type": "object",
            "required": ["filters"],
            "properties": {
                "filters": {
                    "type": "object",
                    "required": ["limit"],
                    "properties": {
                        "limit": {"type": "integer", "minimum": 1},
                    },
                    "additionalProperties": False,
                }
            },
            "additionalProperties": False,
        }
    )
    call = OperationCall(
        id="c-1",
        operation_slug=operation.operation_slug,
        arguments={"filters": {"limit": "10"}},
    )
    result, _ = await OperationExecutor().execute(call, _ctx(), [operation])

    if _JSONSCHEMA_AVAILABLE:
        assert result.success is False
        assert result.metadata.get("error_code") == RuntimeErrorCode.OPERATION_INVALID_ARGS.value
        assert result.metadata.get("field_path") == "$.filters.limit"
        assert result.metadata.get("retryable") is True
    else:
        # Fallback validator (without jsonschema) does not recurse into nested types.
        assert result.success is True


@pytest.mark.asyncio
async def test_operation_executor_rejects_additional_properties_and_enum():
    operation = _operation(
        schema={
            "type": "object",
            "required": ["mode"],
            "properties": {
                "mode": {"type": "string", "enum": ["safe", "strict"]},
            },
            "additionalProperties": False,
        }
    )
    call = OperationCall(
        id="c-2",
        operation_slug=operation.operation_slug,
        arguments={"mode": "unsafe", "extra": 1},
    )
    result, _ = await OperationExecutor().execute(call, _ctx(), [operation])

    assert result.success is False
    assert result.metadata.get("error_code") == RuntimeErrorCode.OPERATION_INVALID_ARGS.value
    assert result.metadata.get("retryable") is True
    # additionalProperties validation runs before enum recursion by design
    assert result.metadata.get("field_path") == "$"


@pytest.mark.asyncio
async def test_operation_executor_marks_missing_operation_as_non_retryable():
    call = OperationCall(
        id="c-3",
        operation_slug="unknown.op",
        arguments={},
    )
    result, _ = await OperationExecutor().execute(call, _ctx(), [])

    assert result.success is False
    assert result.metadata.get("error_code") == RuntimeErrorCode.OPERATION_UNAVAILABLE.value
    assert result.metadata.get("retryable") is False
