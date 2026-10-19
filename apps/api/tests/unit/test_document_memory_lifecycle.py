from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.runtime.memory.document_memory import accumulate_document_memory, document_memory
from app.runtime.orchestrator import _task_memory_context
from app.runtime.orchestrator_contracts import (
    IterationProposal, PlannedTask, PlannerContext, PlanRequest, SchedulerActionKind,
    TaskCompletionDeclaration, TaskExecutionReceipt, TaskRequest, TaskResult, TaskResolution,
)
from app.runtime.plan_store import InMemoryPlanStore, PlanValidationError


def search(*texts, scope="company", source="doc-1", success=True):
    items = [{"kind": "document_passage", "scope_slug": scope, "subject": "Policy", "text": text,
              "score": 0.9, "metadata": {"document_id": source},
              "source_references": [{"document_id": source}]} for text in texts]
    return {"backend": "hipporag", "success": True, "groups": [{"scope_slug": scope,
            "status": "completed" if success else "failed", "success": success,
            "items": items, "count": len(items), "source_references": [{"document_id": source}]}]}


def passages(context, scope="company"):
    return next(group["items"] for group in document_memory(context)[0]["groups"] if group["scope_slug"] == scope)


def test_exact_dedup_preserves_scope_provenance_text_and_first_snapshot():
    text = "Условие " * 1200 + "ИСКЛЮЧЕНИЕ В КОНЦЕ"
    result = search(text)
    original = deepcopy(result)
    first = accumulate_document_memory([], result)
    repeated = deepcopy(result)
    repeated["groups"][0]["items"][0]["score"] = 0.4
    second = accumulate_document_memory(first, repeated)
    second = accumulate_document_memory(second, search(text, scope="project"))
    second = accumulate_document_memory(second, search(text, source="doc-2"))
    assert len(passages(second)) == 2
    assert len(passages(second, "project")) == 1
    assert passages(second)[0]["text"] == text
    assert len(passages(first)) == 1
    assert result == original


def test_accumulation_does_not_evict_old_searches_and_failure_does_not_erase_them():
    context = []
    for number in range(45):
        context = accumulate_document_memory(context, search(str(number)))
    context = accumulate_document_memory(context, search(success=False))
    assert [item["text"] for item in passages(context)] == [str(number) for number in range(45)]
    assert context[0]["groups"][0]["status"] == "failed"
    assert context[0]["partial"] is True


def test_task_receives_shared_facts_but_no_planner_passages():
    facts = {"scope": "user", "subject": "language", "value": "ru"}
    planner = accumulate_document_memory([facts], search("planning-level information"))
    task = TaskRequest(task_id="work", executor="research", intent="work", instructions="work")
    assert _task_memory_context(task, planner) == [facts]
    task.memory_context = accumulate_document_memory([], search("task detail"))
    assert passages(task.memory_context)[0]["text"] == "task detail"
    assert passages(planner)[0]["text"] == "planning-level information"


def interrupted_task():
    store = InMemoryPlanStore()
    plan = store.create(goal="goal", root_run_id=str(uuid4()), tenant_id="tenant",
        scope_context={"selected": [{"key": "company"}], "ceiling_keys": ["company"]})
    proposal = IterationProposal(tasks=[PlannedTask(task_id="original", executor="research", intent="work", instructions="work")], terminal="planner")
    store.apply_iteration(plan["id"], proposal)
    store.claim_task(plan["id"], "original")
    store.update_task_memory(plan["id"], "original", accumulate_document_memory([], search("task detail")))
    execution = TaskExecutionReceipt(declaration=TaskCompletionDeclaration(completion="needs", report="need input",
        needs=[{"ref": "inventory", "key": "inventory", "description": "Read inventory"}]))
    result = TaskResult(outcome="needs_dependency", description="need input", needs=execution.declaration.needs)
    store.finish_attempt(plan["id"], "original", execution=execution, result=result)
    store.claim_checkpoint(plan["id"], SchedulerActionKind.INVOKE_PLANNER)
    return store, plan


def test_only_explicit_continuation_restores_task_memory():
    store, plan = interrupted_task()
    proposal = IterationProposal(tasks=[
        PlannedTask(task_id="helper", executor="research", intent="fetch", instructions="fetch"),
        PlannedTask(task_id="continued", executor="research", continuation_of="original", intent="continue", instructions="continue"),
    ], terminal="planner", resolutions=[TaskResolution(task_id="original", action="continue_with_tasks",
        replacement_task_ids=["helper", "continued"], reason="resolve need and continue")])
    store.apply_iteration(plan["id"], proposal)
    assert plan["tasks"]["helper"]["memory_context"] == []
    assert passages(plan["tasks"]["original"]["memory_context"])[0]["text"] == "task detail"
    assert passages(plan["tasks"]["continued"]["memory_context"])[0]["text"] == "task detail"
    store.claim_task(plan["id"], "helper")
    helper = TaskExecutionReceipt(declaration=TaskCompletionDeclaration(completion="fulfilled", report="done"))
    store.finish_attempt(plan["id"], "helper", execution=helper, result=TaskResult(outcome="completed", description="done"))
    store.claim_task(plan["id"], "continued")
    restored = store.task_request(plan["id"], "continued")["memory_context"]
    store.update_task_memory(plan["id"], "continued", accumulate_document_memory(restored, search("new detail")))
    assert len(passages(plan["tasks"]["continued"]["memory_context"])) == 2
    assert len(passages(plan["tasks"]["original"]["memory_context"])) == 1


def test_continuation_cannot_read_an_unrelated_or_other_executor_task():
    store, plan = interrupted_task()
    proposal = IterationProposal(tasks=[PlannedTask(task_id="steal", executor="other", continuation_of="original",
        intent="work", instructions="work")], terminal="planner", resolutions=[TaskResolution(task_id="original",
        action="continue_with_tasks", replacement_task_ids=["steal"], reason="continue")])
    with pytest.raises(PlanValidationError, match="continuation_of"):
        store.apply_iteration(plan["id"], proposal)


@pytest.mark.asyncio
async def test_planner_searches_update_persisted_owner_snapshot_and_next_prompt(monkeypatch):
    from app.runtime.planner import graph_planner
    records = [{"tool": "memory.search", "arguments": {"query": query}, "result": search(*texts)}
               for query, texts in [("q1", ["first"]), ("q2", ["first", "second"])]]
    tools = SimpleNamespace(descriptors=AsyncMock(return_value=[]), execute=AsyncMock(side_effect=records))
    factory = lambda **kwargs: tools
    factory.MAX_CALLS = 3
    monkeypatch.setattr(graph_planner, "RoleMemoryTools", factory)
    planner = graph_planner.GraphPlanner(session=AsyncMock(), llm_client=AsyncMock())
    planner._llm.role_service.get_role_config = AsyncMock(return_value={})
    planner._llm._compile_role_prompt = lambda *args, **kwargs: "runtime contract"
    steps = [graph_planner.PlannerStep(kind="tool_call", tool_call={"tool": "memory.search", "arguments": {"query": q}})
             for q in ("q1", "q2")]
    steps.append(graph_planner.PlannerStep(kind="proposal", proposal=IterationProposal(tasks=[], terminal="synthesis",
        synthesis_brief={"user_question": "goal", "planned_work": "read", "purpose": "answer", "answer_requirements": "answer"})))
    inputs = []
    async def invoke(**kwargs):
        inputs.append(deepcopy(kwargs["payload"]))
        return SimpleNamespace(value=steps[len(inputs) - 1])
    planner._llm.invoke = invoke
    request = PlanRequest(context=PlannerContext(goal="goal", trigger="initial", execution_ledger={}), plan_id=uuid4())
    persisted, events = [], []
    async def persist(context): persisted.append(deepcopy(context))
    async def sink(event): events.append(event)
    await planner.plan(request=request, persist_memory=persist, event_sink=sink)
    assert [item["text"] for item in passages(inputs[2]["memory_context"])] == ["first", "second"]
    assert "first" not in str(inputs[2]["memory_tool_results"])
    assert len(persisted) == 2
    assert [item["text"] for item in passages(events[-1].data["memory_context"])] == ["first", "second"]
    assert all(event.data["memory_owner"] == "planner" for event in events)


@pytest.mark.asyncio
async def test_agent_logs_complete_tool_response_and_owner_snapshot_without_repeating_passages():
    from app.agents.context import ToolCall, ToolContext, ToolResult
    from app.agents.runtime.agent import AgentLoopState, AgentToolRuntime
    runtime = AgentToolRuntime(llm_client=AsyncMock())
    ctx = ToolContext(user_id=uuid4(), tenant_id=uuid4(), extra={"runtime_task_id": "task-1",
        "task_memory_context": accumulate_document_memory([], search("previous finding"))})
    raw = search("previous finding", "new finding " * 1000)
    runtime.tools.execute = AsyncMock(return_value=(ToolResult.ok(raw, delivery="direct"), []))
    session = SimpleNamespace(run_id=uuid4(), record_event=AsyncMock(), finish=AsyncMock())
    messages, outputs = [], []
    events = [event async for event in runtime._execute_single_operation_call(
        operation_call=ToolCall(id="search-1", tool_name="memory.search", arguments={"query": "detail"}),
        agent_slug="research", agent_execution_id="execution-1", llm_call_id="llm-1", ctx=ctx,
        available_operations=[], policy=SimpleNamespace(max_tool_calls_total=10, tool_timeout_ms=1000),
        run_session=session, all_operation_outputs=outputs, all_sources=[], loop_state=AgentLoopState(),
        operation_results_for_context=messages, operation_calls_total_ref=[0], remaining_wall_time_ms=10_000)]
    response = next(event for event in events if event.type.value == "tool_result")
    snapshot = next(event for event in events if event.data.get("stage") == "memory_context_used")
    assert response.data["data"]["groups"][0]["items"][1]["text"] == raw["groups"][0]["items"][1]["text"]
    assert len(passages(snapshot.data["memory_context"])) == 2
    assert snapshot.data["memory_owner_id"] == "task-1"
    assert "previous finding" not in messages[0][1]
    assert "new finding" not in messages[0][1]
    assert len(passages(ctx.extra["task_memory_context"])) == 2


@pytest.mark.asyncio
async def test_executor_persists_memory_updates_before_returning_needs():
    from app.agents.context import ToolContext
    from app.runtime.agent_executor import AgentExecutor
    from app.runtime.events import RuntimeEvent
    executor = AgentExecutor(session=AsyncMock(), llm_client=AsyncMock())
    request = TaskRequest(task_id="task-1", executor="research", intent="work", instructions="work")
    ctx = ToolContext(user_id=uuid4(), tenant_id=uuid4())
    accumulated = accumulate_document_memory([], search("use after resolving need"))
    async def execute(**kwargs):
        yield RuntimeEvent.status("memory_context_used", memory_context=accumulated)
        ctx.extra["agent_execution_result"] = TaskCompletionDeclaration(completion="needs", report="need input",
            needs=[{"ref": "data", "key": "data", "description": "fetch data"}])
    executor.execute = execute
    persist = AsyncMock()
    result = await executor.execute_attempt(request=request, runtime_state=SimpleNamespace(), messages=[],
        ctx=ctx, user_id=ctx.user_id, tenant_id=ctx.tenant_id, memory_persist=persist)
    persist.assert_awaited_once_with(accumulated)
    assert result.declaration.completion_claim.value == "needs"
    assert request.memory_context == accumulated
