"""Registered memory tools for root roles, using the agent operation executor."""
from __future__ import annotations

from dataclasses import replace
from typing import Any, Awaitable, Callable, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from app.agents.context import ToolCall, ToolContext
from app.agents.operation_executor import DirectOperationExecutor
from app.agents.operation_router import OperationRouter
from app.runtime.events import RuntimeEvent
from app.runtime.memory.search_contract import HippoMemorySearchInput


class MemoryToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["memory.search"]
    arguments: HippoMemorySearchInput


class RoleMemoryTools:
    """Resolve only memory.search; never reuse or alter an agent's execution graph."""

    MAX_CALLS = 3

    def __init__(self, *, session: Any, ctx: ToolContext | None) -> None:
        self._session = session
        self._ctx = ctx
        self._execution_ctx: ToolContext | None = None
        self._executor = DirectOperationExecutor()

    async def descriptors(self) -> list[dict[str, Any]]:
        if self._ctx is None or "memory.search" in self._ctx.denied_tools:
            return []
        if self._execution_ctx is None:
            resolved = await OperationRouter(self._session).resolve(
                user_id=self._ctx.user_id, tenant_id=self._ctx.tenant_id,
                collection_ids=[], system_operation_slugs={"memory.search"},
            )
            resolved.execution_graph.filter_by_operation_slugs({"memory.search"})
            extra = dict(self._ctx.extra)
            deps = replace(self._ctx.get_runtime_deps(), execution_graph=resolved.execution_graph,
                           resolved_operations=resolved.resolved_operations)
            self._execution_ctx = replace(self._ctx, extra=extra)
            self._execution_ctx.set_runtime_deps(deps)
        if not self._execution_ctx.get_runtime_deps().execution_graph.get("memory.search"):
            return []
        return [{"operation": "memory.search",
                 "description": "Search the shared HippoRAG document memory. Choose a focused query; results include passages and sources, not current external-system state.",
                 "input_schema": HippoMemorySearchInput.model_json_schema()}]

    async def execute(
        self, call: MemoryToolCall, *, actor: str, parent_type: str,
        parent_id: str | None, event_sink: Callable[[RuntimeEvent], Awaitable[None]] | None,
    ) -> dict[str, Any]:
        arguments = call.arguments.model_dump()
        call_id = str(uuid4())
        trace = dict(parent_entity_type=parent_type, parent_entity_id=parent_id,
                     actor_type=actor, actor_entity_id=parent_id)
        if event_sink:
            await event_sink(RuntimeEvent.tool_call(tool=call.operation, call_id=call_id,
                                                    arguments=arguments, **trace))
        available = await self.descriptors()
        if not available:
            data = {"success": False, "error_code": "memory_search_unavailable",
                    "error": "memory.search is unavailable in this execution context"}
        else:
            assert self._execution_ctx is not None
            result = await self._executor.execute(
                ToolCall(id=call_id, tool_name=call.operation, arguments=arguments), self._execution_ctx,
            )
            data = {**(result.data or {}), "success": result.success}
            if not result.success:
                data.update(error_code="memory_search_failed", error="Не удалось выполнить поиск в памяти")
        if event_sink:
            await event_sink(RuntimeEvent.tool_result(
                tool=call.operation, call_id=call_id, success=data["success"], data=data,
                error_code=data.get("error_code"), safe_message=data.get("error"), **trace,
                result_delivery="direct", result_inline_complete=True,
            ))
        return {"operation": call.operation, "arguments": arguments, "result": data}
