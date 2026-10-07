import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.agents.runtime import agent as agent_module
from app.agents.runtime.agent import AgentToolRuntime
from app.agents.runtime.policy import GenerationParams, PolicyLimits
from app.runtime.agent_executor import AgentExecutor
from app.runtime.events import RuntimeEventType
from app.runtime.orchestrator_contracts import TaskRequest
from app.runtime.task_completion_prompt import build_task_completion_prompt
from app.services.runtime_event_logger import RuntimeLoggingLevel


@pytest.mark.asyncio
@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("repair", [False, True])
async def test_correction_can_repair_prose_then_wrong_slot_without_losing_native_tools(monkeypatch, native, repair):
    task = TaskRequest(task_id="task", executor="viewer", intent="list", instructions="List",
                       expected_outputs=[{"key": "list", "description": "List", "schema": {"type": "array"}}])
    valid = json.dumps({"completion": "fulfilled", "report": "done", "outputs": {
        "list": {"kind": "value", "value": []}}, "needs": []})
    responses = ["Here is the list.", json.dumps({"completion": "fulfilled", "report": "done",
                                                 "outputs": {"list": []}, "needs": []}), valid]
    if not repair:
        responses[-1] = responses[1]
    runtime = AgentToolRuntime(Mock())
    runtime.llm.call = AsyncMock(side_effect=responses)
    runtime.llm.call_raw = AsyncMock(side_effect=[{"content": text} for text in responses])
    runtime.llm.normalize_response = lambda response: response["content"]
    runtime.config_resolver.resolve = AsyncMock(return_value=(
        PolicyLimits(max_llm_calls=5, max_retries=2), GenerationParams(model="test"),
        {"native_tool_calling": native}, SimpleNamespace(sources={})))
    runtime.logging_resolver.resolve_logging_level = AsyncMock(return_value=RuntimeLoggingLevel.NONE)
    runtime.prompt_assembler.assemble = Mock(return_value=SimpleNamespace(system_prompt="Sandbox override: answer in prose"))
    session = SimpleNamespace(run_id=uuid4(), start=AsyncMock(), record_event=AsyncMock(), finish=AsyncMock())
    runtime._create_run_session = Mock(return_value=session)
    monkeypatch.setattr(agent_module, "serialize_published_operations", lambda operations: [])
    monkeypatch.setattr(agent_module, "serialize_published_collections", lambda *args: [])
    monkeypatch.setattr(agent_module, "build_tools_payload", lambda operations: [{"type": "function"}])
    monkeypatch.setattr(agent_module, "parse_native_tool_calls", lambda response: None)
    deps = SimpleNamespace(sandbox_overrides={"prompt": "Sandbox override: answer in prose"}, resolved_operations=[])
    ctx = SimpleNamespace(extra={"task_completion_response_format": {"type": "json_schema"},
                                 "task_completion_prompt": build_task_completion_prompt(task),
                                 "task_completion_validator": lambda raw: AgentExecutor._terminal_validation_errors(
                                     raw, task=task, verified={})},
                          get_runtime_deps=lambda: deps, set_runtime_deps=lambda value: None, log_intent=AsyncMock())
    request = SimpleNamespace(agent=SimpleNamespace(slug="viewer"), resolved_operations=[object()],
                              resolved_data_instances=[], rbac_audit={}, partial_mode_warning=None, run_id=uuid4())
    events = [event async for event in runtime.execute(request, [{"role": "user", "content": "List"}], ctx)]
    final = [event for event in events if event.type == RuntimeEventType.FINAL]
    assert len(final) == 1
    assert final[0].data["content"] == responses[-1]
    assert bool(ctx.extra["task_completion_validator"](responses[-1])) is not repair
    calls = runtime.llm.call_raw if native else runtime.llm.call
    assert calls.await_count == 3
    if native:
        runtime.llm.call.assert_not_awaited()
        assert all(call.kwargs["tools"] for call in calls.await_args_list)
        assert all(call.kwargs["response_format"] is None for call in calls.await_args_list)
    requests = [event.data for event in events if event.type == RuntimeEventType.LLM_REQUEST]
    assert len({event["llm_call_id"] for event in requests}) == 3
    for event in requests:
        system = event["messages"][0]["content"]
        assert system.startswith("Sandbox override: answer in prose")
        assert system.count("RUNTIME TASK COMPLETION DECLARATION") == 1
        assert '"list"' in system
        assert '"kind": "value"' in system
    assert any("внутрь value" in message["content"] for event in requests
               for message in event["messages"] if message["role"] == "user")
