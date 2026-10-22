"""Requester-local pause/resume through production graph and agent loops."""
from copy import deepcopy
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.runtime.interaction import (InteractionQuestion, InteractionRequester, InteractionRequired,
    RuntimeInteraction, require_interaction_allowed)
from app.runtime.events import RuntimeEvent, RuntimeEventType
from app.runtime.orchestrator import GraphOrchestrator
from app.runtime.orchestrator_contracts import (IterationProposal, PlannedTask, SynthesisBrief,
    TaskCompletionDeclaration, TaskExecutionReceipt)
from app.runtime.plan_store import InMemoryPlanStore, PlanValidationError
from app.schemas.runtime_continuation import RuntimeResumeRequest
from app.services.runtime_hitl_protocol_service import RuntimeHitlProtocolService
from app.services.runtime_resume_checkpoint_service import RuntimeResumeCheckpointService, RuntimeResumeValidationError


class Store:
    def __init__(self):
        self.inner = InMemoryPlanStore()
        self.plan = self.inner.create(goal="goal", root_run_id=str(uuid4()), tenant_id=str(uuid4()),
            scope_context={"selected": [{"key": "company"}], "ceiling_keys": ["company"]})

    def __getattr__(self, name):
        async def invoke(plan_id, *args, **kwargs):
            return getattr(self.inner, name)(str(plan_id), *args, **kwargs)
        return invoke

    async def get_by_run(self, run_id):
        return SimpleNamespace(**self.inner.snapshot(self.plan["id"])) if self.plan["root_run_id"] == str(run_id) else None


class Synthesizer:
    async def stream(self, *, runtime_state, run_id, **kwargs):
        runtime_state.final_answer = "done"
        yield RuntimeEvent.final("done", run_id=str(run_id))


def proposal(tasks=()):
    return IterationProposal(tasks=list(tasks), terminal="synthesis", synthesis_brief=SynthesisBrief(
        user_question="goal", planned_work="work", purpose="answer", answer_requirements="short"))


def question(stage="agent", response_type="text", *, plan_id=None, task_id="work", operation=None):
    return RuntimeInteraction.create(InteractionQuestion(question="Какой проект?", response_type=response_type),
        InteractionRequester(stage=stage, entity_id=str(uuid4()), plan_id=plan_id,
            task_id=task_id if stage == "agent" else None, agent_slug="research" if stage == "agent" else None),
        checkpoint={"messages": [{"role": "user", "content": "original task and observed results"}]}, operation=operation)


@pytest.mark.parametrize("response_type,value", [("text", "Альфа"), ("boolean", True), ("boolean", False)])
def test_same_answer_contract_preserves_typed_values_and_hides_execution_state(response_type, value):
    interaction = question(response_type=response_type)
    request = RuntimeResumeRequest(action="answer", pause_id=interaction.id, response=value)
    _, _, actual = RuntimeResumeCheckpointService.resolve_request(request, {"interaction": interaction.model_dump(mode="json")})
    assert actual == value and type(actual) is type(value)
    pause = RuntimeHitlProtocolService.build_paused_from_stop({"reason": interaction.reason,
        "context": {"interaction": interaction.model_dump(mode="json")},
        "action": {"interaction": interaction.model_dump(mode="json")}})
    public = RuntimeHitlProtocolService.public_pause(pause)
    assert "checkpoint" not in public["context"]["interaction"]
    assert "checkpoint" not in public["action"]["interaction"]
    assert public["action"]["pause_id"] == interaction.id
    assert public["context"]["interaction"]["requester"]["task_id"] == "work"


@pytest.mark.parametrize("response_type,value", [("text", " "), ("text", True), ("text", "x" * 4001),
    ("boolean", "true"), ("boolean", 1), ("boolean", None)])
def test_wrong_response_type_cannot_resume(response_type, value):
    interaction = question(response_type=response_type)
    with pytest.raises(RuntimeResumeValidationError):
        RuntimeResumeCheckpointService.resolve_request(
            RuntimeResumeRequest(action="answer", pause_id=interaction.id, response=value),
            {"interaction": interaction.model_dump(mode="json")})


@pytest.mark.parametrize("action", ["answer", "cancel"])
def test_stale_interaction_cannot_answer_or_cancel_a_new_question(action):
    interaction = question()
    with pytest.raises(RuntimeResumeValidationError, match="устарело"):
        RuntimeResumeCheckpointService.resolve_request(
            RuntimeResumeRequest(action=action, pause_id="old", response="Альфа"),
            {"interaction": interaction.model_dump(mode="json")})


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["Альфа", True, False])
async def test_agent_question_resumes_only_that_task_and_does_not_replay_completed_tasks(value):
    store = Store()
    calls = []
    class Planner:
        async def plan(self, **kwargs):
            return proposal([PlannedTask(task_id=key, executor="research", intent=key, instructions=key)
                             for key in ["finished", "work"]])
    class Executor:
        async def execute_attempt(self, *, request, **kwargs):
            calls.append(request.task_id)
            if request.task_id == "work" and not request.interaction_history:
                raise InteractionRequired(question(response_type="text" if isinstance(value, str) else "boolean"))
            if request.task_id == "work":
                assert request.interaction_history[-1]["response"] == value
                assert request.resume_checkpoint["messages"][0]["content"] == "original task and observed results"
            return TaskExecutionReceipt(declaration=TaskCompletionDeclaration(completion="fulfilled", answer="done"))
    runtime = GraphOrchestrator(store=store, planner=Planner(), executor=Executor(), synthesizer=Synthesizer())
    kwargs = dict(plan_id=store.plan["id"], goal="goal", available_agents=[{"slug": "research", "supports_dynamic_contracts": True}],
                  planner_kwargs={"runtime_state": SimpleNamespace(final_answer=None)})
    first = [event async for event in runtime.run(**kwargs)]
    assert first[-1]["status"] == "waiting_input"
    snapshot = store.inner.snapshot(store.plan["id"])
    interaction = RuntimeInteraction.model_validate(snapshot["pauses"][-1]["payload"]["interaction"])
    assert interaction.requester.task_id == "work" and interaction.requester.plan_id == store.plan["id"]
    store.inner.resume_interaction(store.plan["id"], interaction.id, value)
    second = [event async for event in runtime.run(**kwargs)]
    assert second[-1]["status"] == "completed"
    assert calls == ["finished", "work", "work"]
    with pytest.raises(PlanValidationError):
        store.inner.resume_interaction(store.plan["id"], interaction.id, value)


@pytest.mark.asyncio
async def test_cancelling_paused_plan_cancels_waiting_task_and_interaction():
    store = Store()
    class Planner:
        async def plan(self, **kwargs):
            return proposal([PlannedTask(task_id="work", executor="research", intent="work", instructions="work")])
    class Executor:
        async def execute_attempt(self, **kwargs):
            raise InteractionRequired(question())
    runtime = GraphOrchestrator(store=store, planner=Planner(), executor=Executor(), synthesizer=Synthesizer())
    [event async for event in runtime.run(plan_id=store.plan["id"], goal="goal",
        available_agents=[{"slug": "research", "supports_dynamic_contracts": True}],
        planner_kwargs={"runtime_state": SimpleNamespace(final_answer=None)})]
    store.inner.cancel_plan(store.plan["id"], reason="user_cancelled")
    snapshot = store.inner.snapshot(store.plan["id"])
    assert snapshot["status"] == "cancelled"
    assert snapshot["tasks"]["work"]["status"] == "cancelled"
    assert snapshot["pauses"][-1]["status"] == "cancelled"
    with pytest.raises(PlanValidationError):
        store.inner.resume_interaction(store.plan["id"], snapshot["pauses"][-1]["payload"]["interaction"]["id"], "Альфа")


@pytest.mark.asyncio
async def test_planner_question_restarts_same_planner_checkpoint_with_answer():
    store = Store()
    received = []
    class Planner:
        async def plan(self, *, interaction_answers, **kwargs):
            received.append(deepcopy(interaction_answers))
            if not interaction_answers:
                raise InteractionRequired(question(stage="planner"))
            return proposal()
    runtime = GraphOrchestrator(store=store, planner=Planner(), executor=Mock(), synthesizer=Synthesizer())
    kwargs = dict(plan_id=store.plan["id"], goal="goal", available_agents=[],
                  planner_kwargs={"runtime_state": SimpleNamespace(final_answer=None)})
    assert ([event async for event in runtime.run(**kwargs)])[-1]["status"] == "waiting_input"
    interaction_id = store.inner.snapshot(store.plan["id"])["pauses"][-1]["payload"]["interaction"]["id"]
    store.inner.resume_interaction(store.plan["id"], interaction_id, "Альфа")
    assert ([event async for event in runtime.run(**kwargs)])[-1]["status"] == "completed"
    assert len(received) == 2 and received[-1][-1]["response"] == "Альфа"
    assert len(store.inner.snapshot(store.plan["id"])["iterations"]) == 1


def test_rejected_operation_returns_to_planner_without_rerunning_agent():
    store = Store()
    plan_id = store.plan["id"]
    store.inner.apply_iteration(plan_id, proposal([PlannedTask(task_id="work", executor="research", intent="write", instructions="write")]))
    store.inner.claim_task(plan_id, "work")
    interaction = question(plan_id=plan_id, response_type="boolean", operation={"operation_fingerprint": "exact-write"})
    store.inner.pause_interaction(plan_id, interaction)
    store.inner.resume_interaction(plan_id, interaction.id, False)
    snapshot = store.inner.snapshot(plan_id)
    assert snapshot["tasks"]["work"]["status"] == "cancelled"
    assert snapshot["tasks"]["work"]["result"]["reason_code"] == "confirmation_rejected"
    assert store.inner.next_decision(plan_id).kind.value == "invoke_planner"


def test_interaction_policy_can_deny_an_agent_without_changing_continuation_contract():
    ctx = SimpleNamespace(extra={"interaction_policy": {"agent": {"research": False, "default": True}}})
    with pytest.raises(ValueError, match="disabled"):
        require_interaction_allowed(ctx, "agent", "research")
    require_interaction_allowed(ctx, "agent", "other")


@pytest.mark.asyncio
@pytest.mark.parametrize("value", ["Альфа", True, False])
async def test_chat_resume_uses_same_typed_contract_for_text_and_boolean(monkeypatch, value):
    from app.api.v1.routers.chat import messages
    from app.api.deps import ChatContext
    from app.core.security import UserCtx
    user_id, tenant_id, run_id = uuid4(), uuid4(), uuid4()
    interaction = question(stage="turn_preflight", response_type="text" if isinstance(value, str) else "boolean")
    turn = SimpleNamespace(id=uuid4(), chat_id=uuid4(), user_id=user_id, status="paused",
        pause_status=interaction.reason, paused_action={"kind": "input", "pause_id": interaction.id},
        paused_context={"interaction": interaction.model_dump(mode="json"), "original_goal": "goal"})
    class Result:
        def __init__(self, row): self.row = row
        def scalar_one_or_none(self): return self.row
    session = AsyncMock()
    session.execute.side_effect = [Result(turn), Result(None), Result(turn)]
    captured = {}
    class Service:
        def __init__(self, **kwargs): pass
        async def send_message_stream(self, **kwargs):
            captured.update(kwargs)
            yield {"type": "final", "message_id": str(uuid4()), "content": "done"}
    monkeypatch.setattr(messages, "ChatStreamService", Service)
    monkeypatch.setattr(messages, "resolve_chat_context", AsyncMock(return_value=ChatContext(
        chat_id=str(turn.chat_id), tenant_id=str(tenant_id), user_id=str(user_id),
    )))
    response = await messages.resume_run(run_id=str(run_id), body=RuntimeResumeRequest(
        action="answer", pause_id=interaction.id, response=value), session=session,
        current_user=UserCtx(id=str(user_id), tenant_ids=[str(tenant_id)]), _rl=None)
    assert [chunk async for chunk in response.body_iterator]
    checkpoint = captured["continuation_meta"]["resume_checkpoint"]
    assert checkpoint["interaction_response"] == value
    assert checkpoint["interaction"]["requester"]["stage"] == "turn_preflight"
    assert captured["resumed_turn_id"] == str(turn.id) and turn.status == "resumed"
    assert captured["persist_user_message"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["planner", "agent"])
async def test_real_pipeline_resumes_saved_requester_without_calling_preflight(monkeypatch, stage):
    from app.runtime import pipeline as module
    from app.runtime.pipeline import RuntimePipeline
    from app.runtime.contracts import PipelineRequest
    from app.runtime.budgets import RunLimits, EntityLimits
    from app.runtime.memory.effective_scope import EffectiveScopeContext, ScopeIdentity
    from app.runtime.memory.components import MemoryBundle
    from app.runtime.stages.graph_planning_stage import GraphPlanningStage
    from app.agents.context import ToolContext
    store = Store()
    plan_id = store.plan["id"]
    if stage == "agent":
        store.inner.apply_iteration(plan_id, proposal([PlannedTask(task_id="work", executor="research", intent="work", instructions="work")]))
        store.inner.claim_task(plan_id, "work")
    interaction = question(stage=stage, plan_id=plan_id)
    store.inner.pause_interaction(plan_id, interaction)
    class Planner:
        async def plan(self, *, interaction_answers, **kwargs):
            assert interaction_answers[-1]["response"] == "Альфа"
            return proposal()
    class Executor:
        async def execute_attempt(self, *, request, **kwargs):
            assert request.interaction_history[-1]["response"] == "Альфа"
            return TaskExecutionReceipt(declaration=TaskCompletionDeclaration(completion="fulfilled"))
    graph = GraphOrchestrator(store=store, planner=Planner(), executor=Executor(), synthesizer=Synthesizer())
    scope = EffectiveScopeContext(selected=[ScopeIdentity(key="company")], ceiling_keys=["company"])
    monkeypatch.setattr(module, "PlatformConfigLoader", lambda session: SimpleNamespace(load=AsyncMock(return_value=SimpleNamespace(config={}))))
    monkeypatch.setattr(module, "_base_scope_context", AsyncMock(return_value=scope))
    monkeypatch.setattr(module, "ProjectContextResolver", lambda session: SimpleNamespace(resolve=AsyncMock(return_value=SimpleNamespace(as_dict=lambda: {}))))
    preflight = AsyncMock(side_effect=AssertionError("A response to planner/agent must not be re-routed"))
    monkeypatch.setattr(module.TurnPreflight, "decide", preflight)
    monkeypatch.setattr(module, "MechanicalLookupService", Mock(side_effect=AssertionError("Do not restart lookup")))
    monkeypatch.setattr(
        "app.runtime.datastore_context.load_result_catalog",
        AsyncMock(return_value=([], "available")),
    )
    monkeypatch.setattr(module, "SystemLLMRoleService", lambda session: SimpleNamespace(get_role_config=AsyncMock(side_effect=RuntimeError("No role config in test"))))
    monkeypatch.setattr(module, "BudgetResolver", lambda session: SimpleNamespace(resolve_run=AsyncMock(return_value=RunLimits(iterations=5)),
        resolve_orchestrator=AsyncMock(return_value=EntityLimits())))
    async def emit(event, **kwargs): return event
    logger = SimpleNamespace(emit=emit)
    monkeypatch.setattr(module.RuntimeEventJournalFactory, "create", lambda **kwargs: logger)
    runtime = RuntimePipeline(session=Mock(), llm_client=Mock())
    runtime._resolve_available_agents_for_planner = AsyncMock(return_value=([{"slug": "research", "supports_dynamic_contracts": True}], {}))
    runtime._dispatch_chat_post_final_tail = Mock()
    runtime._assembler = SimpleNamespace(memory_builder=SimpleNamespace(build=AsyncMock(return_value=SimpleNamespace(
        planner_memory_context=[], memory_bundle=MemoryBundle(), durable_snapshot=SimpleNamespace(user_facts=[], tenant_facts=[])))),
        build_graph_planning_stage=lambda **kwargs: GraphPlanningStage(store=store, orchestrator=graph, max_steps=5))
    ctx = ToolContext(user_id=uuid4(), tenant_id=uuid4())
    request = PipelineRequest(request_text="Альфа", user_id=str(ctx.user_id), tenant_id=str(ctx.tenant_id),
        runtime_run_id=store.plan["root_run_id"], await_background_tail=False,
        continuation_meta={"resumed_from_run_id": store.plan["root_run_id"], "resume_checkpoint": {
            "source_run_id": store.plan["root_run_id"], "original_goal": "goal", "resume_action": "input", "user_input": "Альфа",
            "paused_context": {"interaction": interaction.model_dump(mode="json")}, "interaction_response": "Альфа"}})
    events = [event async for event in runtime.execute(request, ctx)]
    assert any(event.type is RuntimeEventType.FINAL and event.data["content"] == "done" for event in events)
    assert store.inner.snapshot(plan_id)["status"] == "completed"
    preflight.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("question_type", ["text", "operation_confirmation"])
async def test_agent_loop_preserves_prior_tool_result_across_question_and_answer(monkeypatch, question_type):
    from app.agents.context import ToolCall
    from app.agents.protocol import ParsedResponse
    from app.agents.runtime import agent as module
    from app.agents.runtime.agent import AgentToolRuntime
    from app.agents.runtime.policy import GenerationParams, PolicyLimits
    from app.services.runtime_event_logger import RuntimeLoggingLevel
    runtime = AgentToolRuntime(Mock())
    ask = json.dumps({"completion": "interaction", "interaction": {"question": "Какой проект?", "response_type": "text"}})
    terminal = json.dumps({"completion": "fulfilled", "answer": "Альфа: observed"})
    runtime.llm.call = AsyncMock(side_effect=["read", ask, terminal] if question_type == "text" else ["read", "write", "write", terminal])
    runtime.config_resolver.resolve = AsyncMock(return_value=(PolicyLimits(max_llm_calls=4),
        GenerationParams(model="test"), {"native_tool_calling": False}, SimpleNamespace(sources={})))
    runtime.logging_resolver.resolve_logging_level = AsyncMock(return_value=RuntimeLoggingLevel.NONE)
    runtime.prompt_assembler.assemble = Mock(return_value=SimpleNamespace(system_prompt="Test"))
    runtime._create_run_session = Mock(side_effect=lambda **kwargs: SimpleNamespace(
        run_id=uuid4(), start=AsyncMock(), record_event=AsyncMock(), finish=AsyncMock()))
    monkeypatch.setattr(module, "serialize_published_operations", lambda operations: [])
    monkeypatch.setattr(module, "serialize_published_collections", lambda *args: [])
    from app.agents.runtime import result_workspace_tools
    monkeypatch.setattr(result_workspace_tools, "with_workspace_operations", lambda operations: operations)
    parse = module.parse_llm_response
    monkeypatch.setattr(module, "parse_llm_response", lambda text, **kwargs: ParsedResponse(text="", has_tool_calls=True,
        tool_calls=[ToolCall(id=text, tool_name="test." + text, arguments={})]) if text in {"read", "write"} else parse(text, **kwargs))
    executed = []
    async def read(**kwargs):
        name = kwargs["operation_call"].tool_name
        if name == "test.write" and not kwargs["ctx"].extra.get("approved"):
            yield RuntimeEvent(RuntimeEventType.CONFIRMATION_REQUIRED, {"summary": "Разрешить запись?", "operation_fingerprint": "exact"})
            return
        executed.append(name)
        kwargs["loop_state"].tool_outputs.append({"success": True, "data": "observed result"})
        kwargs["operation_results_for_context"].append((kwargs["operation_call"], "observed result"))
        yield RuntimeEvent.status("read_done")
    runtime._execute_single_operation_call = read
    deps = SimpleNamespace(sandbox_overrides={}, resolved_operations=[])
    ctx = SimpleNamespace(extra={}, get_runtime_deps=lambda: deps, set_runtime_deps=lambda value: None, log_intent=AsyncMock())
    from app.agents.contracts import ProviderExecutionTarget, ResolvedOperation
    operation = ResolvedOperation(operation_slug="test.read", operation="read", name="Read", source="local",
        data_instance_id="system", data_instance_slug="system", scope="system",
        target=ProviderExecutionTarget(operation_slug="test.read", provider_type="local", handler_slug="test.read",
            data_instance_id="system", data_instance_slug="system"))
    write = operation.model_copy(update={"operation_slug": "test.write", "operation": "write"})
    request = SimpleNamespace(agent=SimpleNamespace(slug="research"), agent_version=None, resolved_operations=[operation, write],
        resolved_data_instances=[], rbac_audit={}, partial_mode_warning=None, run_id=uuid4())
    first = [event async for event in runtime.execute(request, [{"role": "user", "content": "original task"}], ctx)]
    pause = next(event for event in first if event.type in {RuntimeEventType.WAITING_INPUT, RuntimeEventType.CONFIRMATION_REQUIRED})
    ctx.extra.update(approved=True, interaction_resume_checkpoint=pause.data["checkpoint"], interaction_answers=[{"question": "Какой проект?", "response": "Альфа"}])
    second = [event async for event in runtime.execute(request, [{"role": "user", "content": "new unrelated input"}], ctx)]
    assert executed == (["test.read"] if question_type == "text" else ["test.read", "test.write"])
    assert any(event.type is RuntimeEventType.FINAL for event in second)
    messages = runtime.llm.call.await_args.kwargs["messages"]
    assert "observed result" in str(messages) and "Альфа" in str(messages)
    assert "new unrelated input" not in str(messages)
