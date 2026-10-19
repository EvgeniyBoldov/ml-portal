from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.runtime.turn_preflight import TurnPreflight, TurnPreflightDecision


def final_decision(route="synthesis"):
    if route == "planner":
        return TurnPreflightDecision(route=route, task_brief={
            "goal": "NIMS-3532", "direction": "Check other sources", "expected_result": "Details"})
    return TurnPreflightDecision(route=route, synthesis_brief={
        "synthesis_brief": {"user_question": "NIMS-3532", "planned_work": "Read memory",
                            "purpose": "Answer", "answer_requirements": "Cite sources"},
        "answer_draft": "Memory answer"})


@pytest.mark.asyncio
@pytest.mark.parametrize("items,route", [([{"text": "Issue description"}], "synthesis"),
                                      ([], "synthesis"), ([], "planner")])
async def test_preflight_searches_before_final_route_and_retains_evidence(monkeypatch, items, route):
    from app.runtime import turn_preflight
    search_step = TurnPreflightDecision.model_validate({"route": "tool_call", "tool_call": {
        "tool": "memory.search", "arguments": {"query": "NIMS-3532"}}})
    record = {"tool": "memory.search", "arguments": {"query": "NIMS-3532", "limit": 8},
              "result": {"success": True, "items": items, "count": len(items)}}
    tools = SimpleNamespace(descriptors=AsyncMock(return_value=[{"tool": "memory.search"}]),
                            execute=AsyncMock(return_value=record))
    factory = lambda **kwargs: tools
    factory.MAX_CALLS = 3
    monkeypatch.setattr(turn_preflight, "RoleMemoryTools", factory)
    preflight = TurnPreflight(session=object(), llm_client=AsyncMock())
    preflight._llm.invoke = AsyncMock(side_effect=[SimpleNamespace(value=search_step),
                                                 SimpleNamespace(value=final_decision(route))])
    result = await preflight.decide(user_request="NIMS-3532", mechanical_lookup={})
    assert result.route == route
    assert result.memory_tool_results == [record]
    tools.execute.assert_awaited_once()
    from app.runtime.input_builders import compact_memory_tool_records
    assert preflight._llm.invoke.await_args.kwargs["payload"]["memory_tool_results"] == compact_memory_tool_records([record])


def test_preflight_contract_has_no_legacy_recall():
    schema = TurnPreflightDecision.model_json_schema()
    assert "recall" not in schema["properties"]["route"]["enum"]
    assert "memory_request" not in schema["properties"]
    assert "memory_tool_results" not in schema["properties"]


@pytest.mark.asyncio
async def test_preflight_tool_budget_hands_off_with_all_results(monkeypatch):
    from app.runtime import turn_preflight
    step = TurnPreflightDecision(route="tool_call", tool_call={
        "tool": "memory.search", "arguments": {"query": "NIMS-3532"}})
    record = {"tool": "memory.search", "arguments": {"query": "NIMS-3532"},
              "result": {"success": True, "items": []}}
    tools = SimpleNamespace(descriptors=AsyncMock(return_value=[]), execute=AsyncMock(return_value=record))
    factory = lambda **kwargs: tools
    factory.MAX_CALLS = 3
    monkeypatch.setattr(turn_preflight, "RoleMemoryTools", factory)
    preflight = TurnPreflight(session=object(), llm_client=AsyncMock())
    preflight._llm.invoke = AsyncMock(side_effect=[SimpleNamespace(value=step.model_copy()) for _ in range(4)])
    result = await preflight.decide(user_request="NIMS-3532", mechanical_lookup={})
    assert result.route == "planner"
    assert result.task_brief.goal == "NIMS-3532"
    assert result.memory_tool_results == [record] * 3
    assert tools.execute.await_count == 3


@pytest.mark.asyncio
async def test_tool_error_is_presented_to_preflight_as_failure(monkeypatch):
    from app.runtime import turn_preflight
    step = TurnPreflightDecision(route="tool_call", tool_call={
        "tool": "memory.search", "arguments": {"query": "NIMS-3532"}})
    record = {"tool": "memory.search", "arguments": {"query": "NIMS-3532"},
              "result": {"success": False, "error_code": "memory_search_failed"}}
    tools = SimpleNamespace(descriptors=AsyncMock(return_value=[]), execute=AsyncMock(return_value=record))
    factory = lambda **kwargs: tools
    factory.MAX_CALLS = 3
    monkeypatch.setattr(turn_preflight, "RoleMemoryTools", factory)
    preflight = TurnPreflight(session=object(), llm_client=AsyncMock())
    preflight._llm.invoke = AsyncMock(side_effect=[SimpleNamespace(value=step),
                                                 SimpleNamespace(value=final_decision("planner"))])
    result = await preflight.decide(user_request="NIMS-3532", mechanical_lookup={})
    assert result.route == "planner"
    assert result.memory_tool_results[0]["result"]["success"] is False


@pytest.mark.asyncio
async def test_root_dispatch_uses_registered_executor_and_preserves_agent_context(monkeypatch):
    from uuid import uuid4
    from app.agents.context import ToolContext
    from app.agents.registry import ToolRegistry
    from app.agents.runtime_graph import RuntimeExecutionGraph, OperationExecutionBinding, OperationRuntimeContext
    from app.agents.contracts import ProviderExecutionTarget
    from app.agents.operation_executor import DirectOperationExecutor
    from app.runtime.memory import role_tools
    from app.agents.builtins import memory_search
    from app.runtime.memory.search import MemorySearchService

    registry = ToolRegistry()
    session = AsyncMock()
    session.__aenter__.return_value = session
    monkeypatch.setattr(memory_search, "get_session_factory", lambda: lambda: session)
    native = AsyncMock(return_value={"backend": "hipporag", "groups": [{"scope_slug": "a", "success": True, "status": "completed", "document_count": 1,
        "hits": [{"text": "Issue details", "score": 0.9,
                  "metadata": {"document_id": "doc1", "document_title": "NIMS-3532"}}]}]})
    monkeypatch.setattr(memory_search, "HippoRAGService", lambda _: SimpleNamespace(search_documents=native))
    legacy = AsyncMock(side_effect=AssertionError("Root roles must not read legacy memory"))
    monkeypatch.setattr(MemorySearchService, "search", legacy)
    handler = ToolRegistry.get("memory.search")
    original_execute = handler.execute
    monkeypatch.setattr(handler, "execute", AsyncMock(wraps=original_execute))
    registry.register_handler(handler)
    graph = RuntimeExecutionGraph()
    graph.add(OperationExecutionBinding(operation_slug="memory.search",
        target=ProviderExecutionTarget(operation_slug="memory.search", provider_type="local",
            handler_slug="memory.search", data_instance_id="system", data_instance_slug="system", provider_instance_slug="system"),
        context=OperationRuntimeContext(instance_id="system", instance_slug="system", scope="system",
            provider_instance_id="system", provider_instance_slug="system", domain="system")))
    resolve = AsyncMock(return_value=SimpleNamespace(execution_graph=graph, resolved_operations=[]))
    monkeypatch.setattr(role_tools, "OperationRouter", lambda session: SimpleNamespace(resolve=resolve))
    ctx = ToolContext(user_id=uuid4(), tenant_id=uuid4(), extra={"memory_search_scope_keys": ["a"]})
    original_graph = RuntimeExecutionGraph()
    ctx.get_runtime_deps().execution_graph = original_graph
    tools = role_tools.RoleMemoryTools(session=object(), ctx=ctx)
    tools._executor = DirectOperationExecutor(tool_registry=registry)
    events = []
    async def sink(event):
        events.append(event)
    record = await tools.execute(role_tools.MemoryToolCall(tool="memory.search", arguments={"query": "NIMS-3532"}),
        actor="turn_preflight", parent_type="orchestrator", parent_id=str(uuid4()), event_sink=sink)
    assert record["result"]["group_count"] == 1
    assert handler.execute.await_args.args[1] == {"query": "NIMS-3532", "limit": 8}
    assert handler.execute.await_args.args[0].user_id == ctx.user_id
    native.assert_awaited_once_with("NIMS-3532", scope_keys=["a"], limit=8)
    legacy.assert_not_awaited()
    assert record["result"]["groups"][0]["items"][0]["source_references"][0]["document_id"] == "doc1"
    assert ctx.get_runtime_deps().execution_graph is original_graph
    assert resolve.await_args.kwargs["collection_ids"] == []
    assert resolve.await_args.kwargs["system_operation_slugs"] == {"memory.search"}
    assert [event.data["parent_entity_type"] for event in events] == ["orchestrator", "orchestrator"]
    assert events[-1].data["result_delivery"] == "direct"
    assert not any(event.data.get("agent_slug") == "memory_selector" for event in events)


@pytest.mark.asyncio
async def test_denied_memory_tool_is_neither_exposed_nor_executed():
    from uuid import uuid4
    from app.agents.context import ToolContext
    from app.runtime.memory.role_tools import RoleMemoryTools, MemoryToolCall
    ctx = ToolContext(user_id=uuid4(), tenant_id=uuid4(), denied_tools=["memory.search"])
    tools = RoleMemoryTools(session=object(), ctx=ctx)
    tools._executor.execute = AsyncMock()
    assert await tools.descriptors() == []
    record = await tools.execute(MemoryToolCall(tool="memory.search", arguments={"query": "NIMS-3532"}),
        actor="planner", parent_type="planner_iteration", parent_id=None, event_sink=None)
    assert record["result"]["success"] is False
    tools._executor.execute.assert_not_awaited()


def test_document_passages_survive_scope_projection_and_agent_rendering():
    from app.runtime.memory.effective_scope import project_memory_context
    from app.runtime.agent_executor import _render_memory_recall
    data = {"backend": "hipporag", "groups": [
        {"scope_slug": "a", "success": True, "status": "completed", "items": [
            {"kind": "document_passage", "subject": "Issue", "text": "NIMS-3532 details"}]},
        {"scope_slug": "other", "success": True, "status": "completed", "items": []},
    ]}
    entry = {"type": "planner_memory_result", "result": data}
    scoped = project_memory_context(entry, ["a"])["result"]
    assert len(scoped["groups"]) == 1
    assert scoped["groups"][0]["scope_slug"] == "a"
    assert any("NIMS-3532 details" in line for line in _render_memory_recall(scoped))



@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["success", "failure", "exception", "cancelled"])
async def test_root_memory_search_lifecycle_is_visible_while_waiting(caplog, outcome):
    import asyncio
    import logging
    from app.agents.context import ToolResult
    from app.runtime.memory.role_tools import MemoryToolCall, RoleMemoryTools

    tools = RoleMemoryTools(session=object(), ctx=None)
    tools.descriptors = AsyncMock(return_value=[{"tool": "memory.search"}])
    tools._execution_ctx = object()
    entered = asyncio.Event()
    release = asyncio.Event()
    events = []

    async def execute(*args):
        entered.set()
        await release.wait()
        if outcome == "exception":
            raise RuntimeError("private backend details")
        if outcome == "failure":
            return ToolResult.fail("private backend details")
        return ToolResult.ok({"items": []})

    async def sink(event):
        events.append(event)

    tools._executor.execute = execute
    with caplog.at_level(logging.INFO, logger="app.runtime.memory.role_tools"):
        task = asyncio.create_task(tools.execute(
            MemoryToolCall(tool="memory.search", arguments={"query": "private query"}),
            actor="turn_preflight", parent_type="orchestrator", parent_id="preflight-1", event_sink=sink,
        ))
        await asyncio.wait_for(entered.wait(), timeout=1)
        try:
            assert [event.type.value for event in events] == ["tool_call"]
            assert "memory_search_started" in caplog.text
        finally:
            release.set()
            if outcome == "cancelled":
                task.cancel()
            result = (await asyncio.gather(task, return_exceptions=True))[0]

    assert [event.type.value for event in events] == ["tool_call", "tool_result"]
    start, end = events
    assert start.data["call_id"] == end.data["call_id"]
    assert end.data["parent_entity_id"] == "preflight-1"
    assert end.data["success"] is (outcome == "success")
    assert end.data["duration_ms"] >= 0
    if outcome == "cancelled":
        assert isinstance(result, asyncio.CancelledError)
    if outcome == "exception":
        assert isinstance(result, RuntimeError)
    assert "memory_search_finished" in caplog.text
    records = [record for record in caplog.records if record.name == "app.runtime.memory.role_tools"]
    assert [record.call_id for record in records] == [start.data["call_id"]] * 2
    assert records[-1].status == ("completed" if outcome == "success" else "cancelled" if outcome == "cancelled" else "failed")
    assert records[-1].duration_ms == end.data["duration_ms"]
    assert "private query" not in caplog.text
    assert "private backend details" not in caplog.text


@pytest.mark.asyncio
async def test_preflight_applies_scope_change_before_searching(monkeypatch):
    from app.runtime import turn_preflight
    tools = SimpleNamespace(descriptors=AsyncMock(return_value=[{"tool": "memory.search"}]), execute=AsyncMock())
    factory = lambda **kwargs: tools
    factory.MAX_CALLS = 3
    monkeypatch.setattr(turn_preflight, "RoleMemoryTools", factory)
    monkeypatch.setattr(turn_preflight, "resolve_memory_scopes", AsyncMock(return_value=[]))
    preflight = TurnPreflight(session=object(), llm_client=AsyncMock())
    preflight._llm.invoke = AsyncMock(return_value=SimpleNamespace(value=TurnPreflightDecision(
        route="tool_call", tool_call={"tool": "memory.search", "arguments": {"query": "rules"}},
        scope_selection={"keys": ["new"], "mode": "replace"},
    )))
    result = await preflight.decide(user_request="Switch to new and find rules", mechanical_lookup={},
        project_context={"scope_context": {"keys": ["old"]}})
    assert result.route == "planner"
    assert result.scope_selection.keys == ["new"]
    tools.execute.assert_not_awaited()
