"""Exercise the public request stream, substituting only its stage and I/O boundaries."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from app.agents.context import ToolContext
from app.runtime import pipeline as module
from app.runtime.budgets import EntityLimits, RunLimits
from app.runtime.budgets.errors import BudgetExceededError
from app.runtime.contracts import PipelineRequest, PipelineStopReason
from app.runtime.envelope import PhasedEvent
from app.runtime.events import OrchestrationPhase, RuntimeEvent, RuntimeEventType as EventType
from app.runtime.memory.dto import SummaryDTO
from app.runtime.memory.effective_scope import EffectiveScopeContext, ScopeIdentity
from app.runtime.memory.transport import TurnMemory
from app.runtime.pipeline import RuntimePipeline
from app.runtime.stages.graph_planning_stage import GraphPlanningOutcome, GraphPlanningOutcomeKind
from app.runtime.turn_preflight import TurnPreflightDecision
from app.services.runtime_run_context_service import RuntimeRunContextService


class RecordedJournal:
    def __init__(self):
        self.events = []
        self.close_open_lifecycles = AsyncMock()

    async def emit(self, event, *, phase):
        self.events.append(event)
        return event

    def for_observation_level(self, level):
        return self

    def for_entity(self, **identity):
        return self


@pytest.fixture
def runtime(monkeypatch):
    user_id, tenant_id, chat_id = uuid4(), uuid4(), uuid4()
    request = PipelineRequest(
        request_text="Prepare the project report",
        runtime_run_id=str(uuid4()),
        user_id=str(user_id),
        tenant_id=str(tenant_id),
        chat_id=str(chat_id),
        chat_turn_id=str(uuid4()),
        expected_context_revision=4,
        await_background_tail=False,
    )
    ctx = ToolContext(user_id=user_id, tenant_id=tenant_id, chat_id=chat_id)
    session = Mock(rollback=AsyncMock())
    pipeline = RuntimePipeline(session=session, llm_client=Mock())
    journal = RecordedJournal()
    preflight = AsyncMock()
    real_preflight_decide = module.TurnPreflight.decide
    lookup_data = {"scope_candidates": [{"key": "alpha", "matched_forms": ["Alpha"]}]}
    lookup = AsyncMock(return_value=lookup_data)
    run_limits = AsyncMock(return_value=RunLimits(iterations=5))
    phase_limits = AsyncMock(return_value=EntityLimits())
    scope = EffectiveScopeContext(selected=[ScopeIdentity(key="company")], ceiling_keys=["company"])
    read_context = AsyncMock(return_value=None)
    save_context = AsyncMock()
    apply_outcome = AsyncMock(return_value=SimpleNamespace(revision=5, applied_count=1, skipped_count=0))
    writer = AsyncMock()

    monkeypatch.setattr(module.RuntimeEventJournalFactory, "create", Mock(return_value=journal))
    monkeypatch.setattr(module.PlatformConfigLoader, "load", AsyncMock(return_value=SimpleNamespace(config={})))
    monkeypatch.setattr(module.BudgetResolver, "resolve_run", run_limits)
    monkeypatch.setattr(module.BudgetResolver, "resolve_orchestrator", phase_limits)
    monkeypatch.setattr(module, "_base_scope_context", AsyncMock(return_value=scope))
    monkeypatch.setattr(module, "resolve_memory_scopes",
                        AsyncMock(return_value=[SimpleNamespace(id=uuid4(), key="alpha", name="Alpha")]))
    monkeypatch.setattr(module.ProjectContextResolver, "resolve",
                        AsyncMock(return_value=SimpleNamespace(as_dict=lambda: {})))
    monkeypatch.setattr("app.runtime.datastore_context.load_prior_result_inventory",
                        AsyncMock(return_value=[]))
    monkeypatch.setattr(module.MechanicalLookupService, "lookup", lookup)
    monkeypatch.setattr(module.TurnPreflight, "decide", preflight)
    monkeypatch.setattr(module.SystemLLMRoleService, "get_role_config", AsyncMock(return_value={}))
    monkeypatch.setattr(RuntimeRunContextService, "load", read_context)
    monkeypatch.setattr(RuntimeRunContextService, "save", save_context)

    pipeline._resolve_available_agents_for_planner = AsyncMock(return_value=([{"slug": "research"}], {}))
    pipeline._assembler.memory_builder = SimpleNamespace(build=AsyncMock(
        side_effect=lambda **args: TurnMemory(
            user_id=user_id, tenant_id=tenant_id, chat_id=chat_id, turn_number=1,
            goal=args["goal"], summary=SummaryDTO.empty(chat_id),
        )
    ))
    pipeline._assembler.chat_context_outcome_port = SimpleNamespace(apply=apply_outcome)
    pipeline._assembler.build_memory_writer = Mock(return_value=SimpleNamespace(finalize=writer))
    pipeline._assembler.build_graph_planning_stage = Mock(side_effect=AssertionError("Unexpected planner route"))
    pipeline._dispatch_chat_post_final_tail = Mock()
    pipeline._dispatch_memory_evidence_feedback = Mock()
    return SimpleNamespace(
        pipeline=pipeline, request=request, ctx=ctx, session=session, journal=journal,
        preflight=preflight, lookup=lookup, lookup_data=lookup_data,
        real_preflight_decide=real_preflight_decide,
        run_limits=run_limits, phase_limits=phase_limits, read_context=read_context,
        save_context=save_context, apply_outcome=apply_outcome, writer=writer,
    )


def direct_decision():
    return TurnPreflightDecision.model_validate({
        "route": "synthesis",
        "scope_selection": {"mode": "replace", "keys": ["alpha"]},
        "synthesis_brief": {
            "grounding": "general",
            "answer_draft": "Draft grounded by preflight",
            "synthesis_brief": {
                "user_question": "Prepare the project report",
                "planned_work": "Summarize findings",
                "purpose": "Report",
                "answer_requirements": "Use the project context",
            },
        },
    })


async def collect(runtime, request=None):
    return [event async for event in runtime.pipeline.execute(request or runtime.request, runtime.ctx)]


def event_data(events, kind):
    return [event.data for event in events if event.type is kind]


@pytest.mark.asyncio
async def test_live_combined_lookup_reaches_planner_through_deterministic_preflight(runtime, monkeypatch):
    runtime.request.request_text = "Расскажи про адрес 192.0.2.4/25 из DCBox и в каких задачах Jira он встречается"
    monkeypatch.setattr(module.TurnPreflight, "decide", runtime.real_preflight_decide)
    invoke = AsyncMock(side_effect=AssertionError("Unexpected preflight LLM call"))
    monkeypatch.setattr("app.runtime.llm.structured.StructuredLLMCall.invoke", invoke)

    async def plan(*, task_brief, available_agents, **kwargs):
        assert task_brief["goal"] == runtime.request.request_text
        assert "DCBox" in task_brief["direction"] and "Jira" in task_brief["direction"]
        assert available_agents == [{"slug": "research"}]
        yield PhasedEvent(RuntimeEvent.status("planner received request"), OrchestrationPhase.PLANNER)

    runtime.pipeline._assembler.build_graph_planning_stage.side_effect = None
    runtime.pipeline._assembler.build_graph_planning_stage.return_value = SimpleNamespace(
        run=plan, outcome=GraphPlanningOutcome(GraphPlanningOutcomeKind.FAILED, PipelineStopReason.FAILED),
    )
    events = await collect(runtime)

    [routing] = event_data(events, EventType.PREFLIGHT_ROUTE_DECISION)
    assert routing["proposed_route"] is None
    assert routing["effective_route"] == "planner"
    assert routing["reason"] == "preflight_deterministic"
    assert routing["detail"] == "live_dcbox_jira_lookup"
    assert routing["policy_disposition"] == "accepted"
    assert not event_data(events, EventType.SYNTHESIS_START)
    invoke.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(("grounding", "evidence_refs"), [
    ("corporate", []), ("corporate", ["hallucinated-reference"]), ("general", []),
])
async def test_unsupported_corporate_direct_handoff_reaches_planner(runtime, grounding, evidence_refs):
    runtime.request.request_text = "Как согласуется заявка в нашей компании?"
    decision = direct_decision()
    decision._proposed_route = "synthesis"
    decision.synthesis_brief.grounding = grounding
    decision.synthesis_brief.synthesis_brief.evidence_refs = evidence_refs
    runtime.preflight.return_value = decision

    async def plan(*, task_brief, **kwargs):
        assert task_brief["goal"] == runtime.request.request_text
        assert task_brief["evidence_refs"] == []
        assert task_brief["synthesis_brief"]["user_question"] == runtime.request.request_text
        assert decision.synthesis_brief.answer_draft not in str(task_brief)
        yield PhasedEvent(RuntimeEvent.status("planner received request"), OrchestrationPhase.PLANNER)

    runtime.pipeline._assembler.build_graph_planning_stage.side_effect = None
    runtime.pipeline._assembler.build_graph_planning_stage.return_value = SimpleNamespace(
        run=plan, outcome=GraphPlanningOutcome(GraphPlanningOutcomeKind.FAILED, PipelineStopReason.FAILED),
    )
    events = await collect(runtime)
    [routing] = event_data(events, EventType.PREFLIGHT_ROUTE_DECISION)
    assert (routing["proposed_route"], routing["effective_route"], routing["reason"]) == (
        "synthesis", "planner", "runtime_reroute",
    )
    assert not event_data(events, EventType.SYNTHESIS_START)


@pytest.mark.asyncio
async def test_direct_synthesis_receives_selected_confirmed_facts_and_runtime_date(runtime):
    runtime.request.request_text = "Какой у меня корпоративный логин?"
    decision = direct_decision()
    decision.synthesis_brief.grounding = "corporate"
    decision.synthesis_brief.fact_refs = ["login"]
    runtime.preflight.return_value = decision
    facts = [
        {"id": "login", "scope": "user", "kind": "fact", "subject": "login", "value": "user-a"},
        {"id": "private", "scope": "tenant", "kind": "fact", "subject": "unselected", "value": "SECRET_VALUE"},
    ]
    builder = runtime.pipeline._assembler.memory_builder.build
    turn_memory = builder.side_effect(goal=runtime.request.request_text)
    turn_memory.planner_memory_context = facts
    builder.side_effect = None
    builder.return_value = turn_memory

    async def synthesize(*, runtime_state, synthesis_context, run_id, **kwargs):
        login, today = synthesis_context["memory_context"]
        assert login == facts[0]
        assert today["scope"] == "runtime"
        assert today["subject"] == "current_date"
        assert "SECRET_VALUE" not in str(synthesis_context)
        runtime_state.final_answer = "user-a"
        yield RuntimeEvent.final("user-a", run_id=str(run_id))

    runtime.pipeline._assembler.synthesizer = SimpleNamespace(stream=synthesize)
    assert event_data(await collect(runtime), EventType.FINAL)[0]["content"] == "user-a"


@pytest.mark.asyncio
async def test_corporate_direct_synthesis_receives_selected_fresh_file_contents(runtime):
    from app.runtime.run_context import RunContext

    runtime.request.request_text = "По приложенному файлу расскажи, как согласуется заявка в нашей компании."
    decision = direct_decision()
    decision.synthesis_brief.grounding = "corporate"
    arguments = {"artifact_id": "regulation"}
    result = {"success": True, "artifact_id": "regulation", "content": "Заявку согласует руководитель."}
    decision._memory_tool_results = [{"tool": "file.read", "arguments": arguments, "result": result}]
    file_ref = RunContext().add_evidence("file.read", arguments, result)
    decision.synthesis_brief.synthesis_brief.evidence_refs = [file_ref]
    runtime.preflight.return_value = decision

    async def synthesize(*, runtime_state, synthesis_context, run_id, **kwargs):
        [file] = synthesis_context["run_context"]["evidence"]
        assert file["id"] == file_ref
        assert file["data"] == result
        runtime_state.final_answer = result["content"]
        yield RuntimeEvent.final(runtime_state.final_answer, run_id=str(run_id))

    runtime.pipeline._assembler.synthesizer = SimpleNamespace(stream=synthesize)
    assert event_data(await collect(runtime), EventType.FINAL)[0]["content"] == result["content"]
    runtime.pipeline._assembler.build_graph_planning_stage.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("search", ["found", "empty", "failed"])
async def test_memory_only_direct_synthesis_uses_observed_search_result(runtime, search):
    from app.runtime.run_context import RunContext

    runtime.request.request_text = "Как согласовать заявку? Поищи только в документной памяти."
    decision = direct_decision()
    decision.synthesis_brief.grounding = "memory_only"
    arguments = {"query": "согласование заявки"}
    items = [{"text": "Заявку согласует руководитель."}] if search == "found" else []
    result = {"success": search != "failed", "groups": [{"scope_slug": "alpha", "items": items}]}
    decision._memory_tool_results = [{"tool": "memory.search", "arguments": arguments, "result": result}]
    if search == "found":
        ref = RunContext().add_evidence("memory.search", arguments, result)
        decision.synthesis_brief.synthesis_brief.evidence_refs = [ref]
    runtime.preflight.return_value = decision

    async def synthesize(*, runtime_state, synthesis_context, run_id, **kwargs):
        if search == "found":
            [evidence] = synthesis_context["run_context"]["evidence"]
            assert evidence["data"]["groups"][0]["items"] == items
        else:
            assert synthesis_context["direct_answer_draft"] != decision.synthesis_brief.answer_draft
            assert not synthesis_context["run_context"]["evidence"]
        [status] = synthesis_context["memory_search_status"]
        assert status["success"] == (search != "failed")
        runtime_state.final_answer = synthesis_context["direct_answer_draft"]
        yield RuntimeEvent.final(runtime_state.final_answer, run_id=str(run_id))

    runtime.pipeline._assembler.synthesizer = SimpleNamespace(stream=synthesize)
    assert event_data(await collect(runtime), EventType.FINAL)
    runtime.pipeline._assembler.build_graph_planning_stage.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("tail", ["detached", "inline", "inline_failure"])
async def test_direct_request_reconciles_chat_and_preserves_answer(runtime, tail):
    runtime.preflight.return_value = direct_decision()
    runtime.request.await_background_tail = tail != "detached"
    runtime.request.sandbox_overrides = {"memory_inline": tail != "detached"}
    if tail == "inline_failure":
        runtime.writer.side_effect = RuntimeError("memory storage unavailable")
    delivered = {"artifact_id": str(uuid4()), "file_name": "report.txt", "role": "generated"}

    async def synthesize(*, runtime_state, synthesis_context, run_id, **kwargs):
        assert runtime_state.goal == runtime.request.request_text
        assert synthesis_context["scope_context"]["keys"] == ["alpha"]
        assert synthesis_context["direct_answer_draft"] == "Draft grounded by preflight"
        runtime_state.final_answer = "Report ready"
        runtime_state.run_context.delivered_artifacts = [delivered]
        yield RuntimeEvent.final("Report ready", run_id=str(run_id), attachments=[delivered])

    runtime.pipeline._assembler.synthesizer = SimpleNamespace(stream=synthesize)
    events = await collect(runtime)

    assert event_data(events, EventType.FINAL)[0]["attachments"] == [delivered]
    policy_end = next(i for i, event in enumerate(events) if event.type is EventType.ROUTE_POLICY_END)
    preflight_start = next(i for i, event in enumerate(events) if event.type is EventType.ORCHESTRATOR_START)
    assert policy_end < preflight_start
    assert event_data(events, EventType.PREFLIGHT_ROUTE_DECISION)[0]["effective_route"] == "synthesis"
    runtime.pipeline._assembler.build_graph_planning_stage.assert_not_called()
    runtime.apply_outcome.assert_awaited_once()
    outcome_call = runtime.apply_outcome.await_args.kwargs
    assert outcome_call["expected_context_revision"] == 4
    assert outcome_call["projection"].terminal_state == "completed"
    assert outcome_call["projection"].run_id == runtime.request.runtime_run_id
    assert outcome_call["projection"].artifacts[0]["artifact_id"] == delivered["artifact_id"]
    assert not event_data(runtime.journal.events, EventType.ERROR)
    if tail == "detached":
        assert events[-1].type is EventType.FINAL
        runtime.pipeline._dispatch_chat_post_final_tail.assert_called_once()
        runtime.writer.assert_not_awaited()
    else:
        runtime.writer.assert_awaited_once()
        assert runtime.writer.await_args.kwargs["assistant_final"] == "Report ready"
        assert event_data(events, EventType.RUN_END)[0]["status"] == "completed"
        assert ("memory_write_failed" in [row.get("stage") for row in event_data(events, EventType.STATUS)]) == (
            tail == "inline_failure"
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exception", "public_code", "retryable"),
    [
        (RuntimeError("private provider details"), "turn_preflight_unavailable", True),
        (TimeoutError("private provider details"), "orchestrator_phase_timeout", True),
        (BudgetExceededError(scope="preflight", metric="llm_calls", used=2, limit=1), "budget_exceeded", False),
    ],
)
async def test_preflight_failure_cannot_fall_through_to_planning(runtime, exception, public_code, retryable):
    runtime.preflight.side_effect = exception

    events = await collect(runtime)

    [error] = event_data(events, EventType.ERROR)
    assert (error["error_code"], error["retryable"]) == (public_code, retryable)
    assert "private provider details" not in error["user_message"]
    assert event_data(events, EventType.STOP)[0]["reason"] == "failed"
    assert event_data(events, EventType.RUN_END)[0]["status"] == "failed"
    assert not event_data(events, EventType.FINAL)
    runtime.session.rollback.assert_awaited_once()
    runtime.pipeline._assembler.build_graph_planning_stage.assert_not_called()
    runtime.apply_outcome.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("answer", ["Alpha", False])
async def test_request_resumes_preflight_from_its_own_checkpoint(runtime, answer):
    response_type = "boolean" if isinstance(answer, bool) else "text"
    runtime.preflight.side_effect = [
        TurnPreflightDecision.model_validate({
            "route": "clarify",
            "clarification": {"question": "Use Alpha?", "response_type": response_type},
        }),
        direct_decision(),
    ]

    async def synthesize(*, runtime_state, synthesis_context, run_id, **kwargs):
        assert synthesis_context["user_question"] == runtime.request.request_text
        runtime_state.final_answer = "Report ready"
        yield RuntimeEvent.final("Report ready", run_id=str(run_id))

    runtime.pipeline._assembler.synthesizer = SimpleNamespace(stream=synthesize)
    first = await collect(runtime)
    [pause] = event_data(first, EventType.STOP)
    reason = "waiting_confirmation" if isinstance(answer, bool) else "waiting_input"
    assert pause["reason"] == reason
    assert event_data(first, EventType.RUN_END)[0]["status"] == reason
    assert pause["context"]["interaction"]["requester"]["stage"] == "turn_preflight"
    assert runtime.apply_outcome.await_args.kwargs["projection"].terminal_state == reason
    runtime.read_context.return_value = runtime.save_context.await_args.kwargs["context"]
    resumed = runtime.request.model_copy(update={
        "request_text": str(answer),
        "runtime_run_id": None,
        "continuation_meta": {"resume_checkpoint": {
            "source_run_id": runtime.request.runtime_run_id,
            "original_goal": runtime.request.request_text,
            "resume_action": "input",
            "paused_context": pause["context"],
            "interaction_response": answer,
        }},
    })
    runtime.ctx = ToolContext(user_id=runtime.ctx.user_id, tenant_id=runtime.ctx.tenant_id, chat_id=runtime.ctx.chat_id)

    events = await collect(runtime, resumed)

    assert event_data(events, EventType.RUN_START)[0]["entity_id"] == runtime.request.runtime_run_id
    assert event_data(events, EventType.QUESTION_ANSWER)[0]["response"] == answer
    assert runtime.preflight.await_args.kwargs["user_request"] == runtime.request.request_text
    assert runtime.preflight.await_args.kwargs["mechanical_lookup"] == runtime.lookup_data
    assert runtime.preflight.await_args.kwargs["continuation"]["clarification_history"] == [
        {"question": "Use Alpha?", "answer": answer},
    ]
    runtime.lookup.assert_awaited_once()
    assert runtime.apply_outcome.await_args.kwargs["projection"].terminal_state == "completed"
    runtime.pipeline._assembler.build_graph_planning_stage.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("stop", [PipelineStopReason.WAITING_INPUT, PipelineStopReason.WAITING_CONFIRMATION,
                                  PipelineStopReason.COMPLETED, PipelineStopReason.FAILED])
async def test_planner_route_owns_the_request_until_its_outcome(runtime, stop):
    runtime.preflight.return_value = TurnPreflightDecision.model_validate({
        "route": "planner", "task_brief": {
            "goal": "Normalized goal", "direction": "Inspect project data", "expected_result": "A report",
        },
    })
    outcome = GraphPlanningOutcome(
        kind=GraphPlanningOutcomeKind.PAUSED,
        stop_reason=stop,
        pause_question="Which project?",
        pause_context={"task_id": "research"},
    )

    async def plan(*, runtime_state, task_brief, **kwargs):
        assert runtime_state.goal == task_brief["goal"] == "Normalized goal"
        if stop is PipelineStopReason.COMPLETED:
            outcome.kind = GraphPlanningOutcomeKind.COMPLETED
            runtime_state.final_answer = "Planned report"
            yield PhasedEvent(RuntimeEvent.final("Planned report"), OrchestrationPhase.SYNTHESIS)
        elif stop is PipelineStopReason.FAILED:
            outcome.kind = GraphPlanningOutcomeKind.FAILED

    runtime.pipeline._assembler.build_graph_planning_stage.side_effect = None
    runtime.pipeline._assembler.build_graph_planning_stage.return_value = SimpleNamespace(run=plan, outcome=outcome)
    events = await collect(runtime)

    runtime.pipeline._assembler.build_graph_planning_stage.assert_called_once_with(max_steps=5)
    assert runtime.apply_outcome.await_args.kwargs["projection"].terminal_state == stop.value
    if stop is PipelineStopReason.COMPLETED:
        assert events[-1].type is EventType.FINAL
        runtime.pipeline._dispatch_chat_post_final_tail.assert_called_once()
    else:
        assert [row["status"] for row in event_data(runtime.journal.events, EventType.RUN_END)] == [stop.value]
        runtime.pipeline._dispatch_chat_post_final_tail.assert_not_called()
    if outcome.kind is GraphPlanningOutcomeKind.PAUSED:
        [pause] = event_data(events, EventType.STOP)
        assert pause["reason"] == stop.value
        assert pause["context"]["task_id"] == "research"
        assert pause["context"]["runtime_budget_usage"]["active_wall_time_ms"] >= 0
        assert not event_data(runtime.journal.events, EventType.ERROR)
    elif stop is PipelineStopReason.FAILED:
        assert event_data(events, EventType.ERROR)[0]["error_code"] == "runtime_execution_failed"


@pytest.mark.asyncio
async def test_request_cancellation_closes_run_without_a_final_answer(runtime):
    entered = asyncio.Event()

    async def waiting_preflight(**kwargs):
        entered.set()
        await asyncio.Future()

    runtime.preflight.side_effect = waiting_preflight
    task = asyncio.create_task(collect(runtime))
    await asyncio.wait_for(entered.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    runtime.journal.close_open_lifecycles.assert_awaited_once_with(
        status="cancelled", phase=OrchestrationPhase.PIPELINE,
    )
    assert [row["status"] for row in event_data(runtime.journal.events, EventType.RUN_END)] == ["cancelled"]
    assert not event_data(runtime.journal.events, EventType.FINAL)


@pytest.mark.asyncio
async def test_exhausted_resume_budget_stops_before_preflight(runtime):
    runtime.run_limits.return_value = RunLimits(wall_time_ms=100)
    runtime.request.continuation_meta = {"resume_checkpoint": {
        "budget_usage": {"active_wall_time_ms": 100}
    }}

    events = await collect(runtime)

    assert event_data(events, EventType.ERROR)[0]["error_code"] == "agent_wall_time_exceeded"
    assert event_data(events, EventType.STOP)[0]["reason"] == "budget_exceeded"
    assert [row["status"] for row in event_data(runtime.journal.events, EventType.RUN_END)] == ["failed"]
    runtime.preflight.assert_not_awaited()
    runtime.apply_outcome.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exception", "public_code"),
    [
        (TimeoutError(), "orchestrator_phase_timeout"),
        (BudgetExceededError(scope="synthesizer", metric="llm_calls", used=2, limit=1), "budget_exceeded"),
        (RuntimeError("private synthesis failure"), "synthesis_failed"),
    ],
)
async def test_direct_synthesis_failure_closes_its_phase_and_run(runtime, exception, public_code):
    runtime.preflight.return_value = direct_decision()
    synthesis_id = str(uuid4())

    async def synthesize(*, run_id, **kwargs):
        yield RuntimeEvent.synthesis_start(synthesis_id=synthesis_id, run_id=str(run_id))
        raise exception

    runtime.pipeline._assembler.synthesizer = SimpleNamespace(stream=synthesize)

    events = await collect(runtime)

    [error] = event_data(events, EventType.ERROR)
    assert error["error_code"] == public_code
    assert "private synthesis failure" not in error["user_message"]
    [synthesis_end] = event_data(events, EventType.SYNTHESIS_END)
    assert synthesis_end["entity_id"] == synthesis_id
    assert synthesis_end["status"] == "failed"
    assert [row["status"] for row in event_data(events, EventType.RUN_END)] == ["failed"]
    assert not event_data(events, EventType.FINAL)
    runtime.apply_outcome.assert_not_awaited()
    runtime.writer.assert_not_awaited()


@pytest.mark.asyncio
async def test_active_run_deadline_cancels_synthesis(runtime):
    runtime.run_limits.return_value = RunLimits(wall_time_ms=250)
    runtime.preflight.return_value = direct_decision()
    cancelled = asyncio.Event()

    async def synthesize(*, run_id, **kwargs):
        yield RuntimeEvent.synthesis_start(synthesis_id=str(uuid4()), run_id=str(run_id))
        try:
            await asyncio.Future()
        finally:
            cancelled.set()

    runtime.pipeline._assembler.synthesizer = SimpleNamespace(stream=synthesize)
    executor = Mock(aclose=AsyncMock())
    runtime.pipeline._assembler.agent_executor = executor

    events = await asyncio.wait_for(collect(runtime), timeout=2)

    assert cancelled.is_set()
    assert not event_data(events, EventType.FINAL)
    [stop] = event_data(events, EventType.STOP)
    assert stop == {"reason": "budget_exceeded", "run_id": runtime.request.runtime_run_id}
    assert event_data(events, EventType.ERROR)[0]["error_code"] == "agent_wall_time_exceeded"
    executor.aclose.assert_awaited_once()
    runtime.apply_outcome.assert_not_awaited()


@pytest.mark.asyncio
async def test_request_preparation_failure_is_recorded_and_never_routes(runtime):
    runtime.run_limits.side_effect = RuntimeError("limits unavailable")

    with pytest.raises(RuntimeError, match="limits unavailable"):
        await collect(runtime)

    [error] = event_data(runtime.journal.events, EventType.ERROR)
    assert error["stage"] == "runtime_limits"
    assert error["error_code"] == "runtime_execution_failed"
    assert [row["status"] for row in event_data(runtime.journal.events, EventType.RUN_END)] == ["failed"]
    runtime.lookup.assert_not_awaited()
    runtime.preflight.assert_not_awaited()


@pytest.mark.asyncio
async def test_chat_finalization_persists_intent_then_waits_for_message_commit(runtime, monkeypatch):
    from app.services.runtime_event_logger import RuntimeLoggingLevel
    from app.workers.tasks_memory import finalize_memory_task

    runtime.preflight.return_value = direct_decision()
    runtime.journal.context = SimpleNamespace(level=RuntimeLoggingLevel.FULL)
    runtime.journal.worker_payload = Mock(return_value={})
    message_committed = asyncio.Event()
    intent_committed = asyncio.Event()
    runtime.ctx.extra["chat_post_final_tail_ready"] = message_committed
    del runtime.pipeline._dispatch_chat_post_final_tail

    async def synthesize(*, runtime_state, run_id, **kwargs):
        runtime_state.final_answer = "Report ready"
        yield RuntimeEvent.final("Report ready", run_id=str(run_id))

    runtime.pipeline._assembler.synthesizer = SimpleNamespace(stream=synthesize)
    saved_rows = []

    async def commit_intent():
        intent_committed.set()

    async def get_outbox(model, row_id):
        [row] = saved_rows
        assert row.id == row_id
        return row

    async def sessions():
        # The detached writer opens its own session and two short outbox transactions.
        yield Mock()
        yield Mock(
            execute=AsyncMock(return_value=Mock(scalar_one_or_none=Mock(return_value=None))),
            add=Mock(side_effect=saved_rows.append),
            commit=AsyncMock(side_effect=commit_intent),
        )
        yield Mock(get=AsyncMock(side_effect=get_outbox), commit=AsyncMock())

    available_sessions = sessions()

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def session_factory():
        yield await anext(available_sessions)

    deps = runtime.ctx.get_runtime_deps()
    deps.session_factory = session_factory
    runtime.ctx.set_runtime_deps(deps)
    enqueue = Mock()
    monkeypatch.setattr(finalize_memory_task, "apply_async", enqueue)

    events = await collect(runtime)
    tasks = tuple(runtime.pipeline._chat_tail_tasks)
    try:
        assert events[-1].type is EventType.FINAL
        await asyncio.wait_for(intent_committed.wait(), timeout=2)
        [row] = saved_rows
        assert row.runtime_run_id == runtime.request.runtime_run_id
        assert str(row.chat_turn_id) == runtime.request.chat_turn_id
        assert row.payload["assistant_final"] == "Report ready"
        enqueue.assert_not_called()
        assert not event_data(runtime.journal.events, EventType.RUN_END)
    finally:
        message_committed.set()
        await asyncio.wait_for(asyncio.gather(*tasks), timeout=2)
        await available_sessions.aclose()

    enqueue.assert_called_once_with(
        args=[{"outbox_id": str(row.id)}], task_id=f"memory-finalize-{row.id}",
    )
    assert row.status == "dispatched"
    assert [entry["status"] for entry in event_data(runtime.journal.events, EventType.RUN_END)] == ["completed"]


@pytest.mark.asyncio
async def test_request_filters_rbac_before_memory_and_routing(runtime, monkeypatch):
    from app.services.permission_service import EffectivePermissions

    available = {"slug": "research", "name": "Research"}
    denied = {"slug": "private", "name": "Private"}
    platform = SimpleNamespace(
        config={"default_collection_allow": False},
        available_agents_for_planner=Mock(return_value=[available, denied]),
    )
    monkeypatch.setattr(module.PlatformConfigLoader, "load", AsyncMock(return_value=platform))
    monkeypatch.setattr(module.PermissionService, "resolve_permissions", AsyncMock(
        return_value=EffectivePermissions(agent_permissions={"research": True, "private": False}),
    ))
    monkeypatch.setattr(module.AgentService, "get_agent_by_slug", AsyncMock(
        return_value=SimpleNamespace(agent_type="runtime"),
    ))
    monkeypatch.setattr(module.AgentService, "resolve_published_version", AsyncMock())
    del runtime.pipeline._resolve_available_agents_for_planner
    runtime.request.agent_slug = "private"
    runtime.preflight.return_value = TurnPreflightDecision.model_validate({
        "route": "planner", "task_brief": {
            "goal": "Report", "direction": "Read permitted data", "expected_result": "A report",
        },
    })

    async def plan(*, available_agents, planner_rbac_audit, **kwargs):
        assert available_agents == [available]
        assert planner_rbac_audit["allowed"] == ["research"]
        assert planner_rbac_audit["denied_by_rbac"] == ["private"]
        yield PhasedEvent(RuntimeEvent.status("planner received request"), OrchestrationPhase.PLANNER)

    runtime.pipeline._assembler.build_graph_planning_stage.side_effect = None
    runtime.pipeline._assembler.build_graph_planning_stage.return_value = SimpleNamespace(
        run=plan, outcome=GraphPlanningOutcome(GraphPlanningOutcomeKind.FAILED, PipelineStopReason.FAILED),
    )

    await collect(runtime)

    assert runtime.pipeline._assembler.memory_builder.build.await_args.kwargs["agent_slug"] is None
    platform.available_agents_for_planner.assert_called_once_with("private")
