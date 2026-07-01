"""Targeted runtime coverage — validator, AgentExecutor helpers, Planner.

Post-M5 rewrite: `TurnSummarizer` tests dropped (summarizer removed —
its role is now owned by `SummaryCompactor` which has its own tests in
`test_memory_helpers.py`). Validator tests now cover the new
`DIRECT_ANSWER` and `CLARIFY` kinds.
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.agents.execution_preflight import ExecutionMode
from app.agents.context import ToolCall, ToolContext, ToolResult
from app.agents.runtime.agent import AgentToolRuntime
from app.runtime.agent_executor import AgentExecutor
from app.runtime.contracts import ExecutionMode as RuntimeExecutionMode, NextStep, NextStepKind
from app.runtime.events import RuntimeEventType
from app.runtime.budgets import BudgetLimitsResolver, RunBudgetLedger
from app.runtime.llm.structured import StructuredCallError
from app.agents.runtime.llm import LLMAdapter
from app.runtime.operation_errors import RuntimeErrorCode
from app.runtime.planner.iteration_policy import classify_agent_failure
from app.runtime.planner.planner import Planner, PlannerLLMOutput
from app.runtime.planner.validator import validate_next_step
from app.runtime.stages.planner_call_agent_dispatcher import PlannerCallAgentDispatcher
from app.runtime.stages.planning_stage import PlanningStage
from app.runtime.turn_state import RuntimeTurnState
from app.runtime.memory.components import MemoryBundle


def _memory(*, can_finalize: bool = True):
    mem = SimpleNamespace(
        run_id=uuid4(),
        chat_id=None,
        user_id=None,
        tenant_id=None,
        goal="goal",
        question="",
        outline=None,
        current_phase_id=None,
        completed_phase_ids=[],
        blocked_phase_ids=[],
        open_questions=[],
        status="running",
        final_answer=None,
        final_error=None,
        iter_count=0,
        used_tool_calls=0,
        recent_action_signatures=[],
        planner_steps=[],
        agent_results=[],
        facts=[],
        tool_ledger=None,
    )
    if not can_finalize:
        mem.outline = {"phases": [{"phase_id": "must-do", "must_do": True}]}
    return mem


def ensure_runtime_turn_state(memory) -> RuntimeTurnState:
    state = RuntimeTurnState.from_seed(
        run_id=memory.run_id,
        chat_id=memory.chat_id,
        user_id=memory.user_id,
        tenant_id=memory.tenant_id,
        goal=memory.goal or "",
        current_user_query=memory.question or "",
        memory_bundle=MemoryBundle(),
    )
    state.outline = memory.outline
    state.current_phase_id = memory.current_phase_id
    state.completed_phase_ids = list(memory.completed_phase_ids or [])
    state.blocked_phase_ids = list(memory.blocked_phase_ids or [])
    state.open_questions = list(memory.open_questions or [])
    state.status = memory.status or "running"
    state.final_answer = memory.final_answer
    state.final_error = memory.final_error
    state.iter_count = int(memory.iter_count or 0)
    state.used_tool_calls = int(memory.used_tool_calls or 0)
    state.recent_action_signatures = list(memory.recent_action_signatures or [])
    state.planner_steps = [
        {
            "iteration": int(getattr(item, "iteration", 0) or 0),
            "kind": str(getattr(item, "kind", "") or ""),
            "agent_slug": getattr(item, "agent_slug", None),
            "phase_id": getattr(item, "phase_id", None),
            "rationale": str(getattr(item, "rationale", "") or ""),
        }
        for item in (memory.planner_steps or [])
    ]
    state.agent_results = [
        {
            "agent_slug": str(getattr(item, "agent_slug", "") or ""),
            "summary": str(getattr(item, "summary", "") or ""),
            "facts": list(getattr(item, "facts", []) or []),
            "phase_id": getattr(item, "phase_id", None),
            "iteration": int(getattr(item, "iteration", 0) or 0),
            "success": bool(getattr(item, "success", True)),
            "error": getattr(item, "error", None),
        }
        for item in (memory.agent_results or [])
    ]
    for fact in (memory.facts or []):
        text = str(getattr(fact, "text", "") or "").strip()
        if text:
            state.add_runtime_fact(text, source=str(getattr(fact, "source", "") or "planner"))
    return state


class _FakeRunSession:
    def __init__(self) -> None:
        self.run_id = uuid4()
        self.finished: tuple[str, str | None] | None = None

    async def start(self) -> None:
        return None

    async def log_step(self, *_args, **_kwargs) -> None:
        return None

    async def finish(self, status: str, reason: str | None = None) -> None:
        self.finished = (status, reason)


def test_validator_call_agent_missing_slug_errors():
    mem = _memory()
    assert validate_next_step(
        NextStep(kind=NextStepKind.CALL_AGENT, rationale="r"),
        allowed_agents=["analyst"],
        runtime_state=ensure_runtime_turn_state(mem),
    ) == "call_agent step missing agent_slug"


def test_validator_call_agent_not_in_allowed_list_errors():
    mem = _memory()
    err = validate_next_step(
        NextStep(kind=NextStepKind.CALL_AGENT, rationale="r", agent_slug="ops"),
        allowed_agents=["analyst"],
        runtime_state=ensure_runtime_turn_state(mem),
    )
    assert err is not None and "not in the allowed list" in err


def test_validator_call_agent_blocked_when_no_allowed_agents():
    mem = _memory()
    err = validate_next_step(
        NextStep(kind=NextStepKind.CALL_AGENT, rationale="r", agent_slug="ops"),
        allowed_agents=[],
        runtime_state=ensure_runtime_turn_state(mem),
    )
    assert err == "call_agent step blocked: no allowed agents available"


def test_validator_clarify_and_ask_user_require_question():
    mem = _memory()
    # ASK_USER with empty question
    assert validate_next_step(
        NextStep(kind=NextStepKind.ASK_USER, rationale="r", question=""),
        allowed_agents=[],
        runtime_state=ensure_runtime_turn_state(mem),
    ) == "ask_user step missing question"
    # CLARIFY with empty question (new kind)
    assert validate_next_step(
        NextStep(kind=NextStepKind.CLARIFY, rationale="r", question=""),
        allowed_agents=[],
        runtime_state=ensure_runtime_turn_state(mem),
    ) == "clarify step missing question"


def test_validator_final_requires_final_answer():
    mem = _memory()
    assert validate_next_step(
        NextStep(kind=NextStepKind.FINAL, rationale="r", final_answer=""),
        allowed_agents=[],
        runtime_state=ensure_runtime_turn_state(mem),
    ) == "final step missing final_answer"
    # happy
    assert validate_next_step(
        NextStep(kind=NextStepKind.FINAL, rationale="r", final_answer="hi"),
        allowed_agents=[],
        runtime_state=ensure_runtime_turn_state(mem),
    ) is None


def test_validator_final_and_abort_constraints():
    mem = _memory()
    assert validate_next_step(
        NextStep(kind=NextStepKind.FINAL, rationale="r", final_answer=""),
        allowed_agents=[],
        runtime_state=ensure_runtime_turn_state(mem),
    ) == "final step missing final_answer"

    blocked = _memory(can_finalize=False)
    assert validate_next_step(
        NextStep(kind=NextStepKind.FINAL, rationale="r", final_answer="ok"),
        allowed_agents=[],
        runtime_state=ensure_runtime_turn_state(blocked),
    ) == "final step blocked: must_do phase is not complete yet"

    assert validate_next_step(
        NextStep(kind=NextStepKind.ABORT, rationale=" "),
        allowed_agents=[],
        runtime_state=ensure_runtime_turn_state(mem),
    ) == "abort step missing rationale"

    assert validate_next_step(
        NextStep(kind=NextStepKind.ABORT, rationale="stop"),
        allowed_agents=[],
        runtime_state=ensure_runtime_turn_state(mem),
    ) is None


def test_validator_blocks_repeated_call_agent_after_sufficient_success():
    mem = _memory()
    state = ensure_runtime_turn_state(mem)
    state.add_iteration_result(
        {
            "iteration": 1,
            "step_kind": NextStepKind.CALL_AGENT.value,
            "agent_slug": "analyst",
            "phase_id": "phase-1",
            "outcome": "success",
            "summary": "done",
            "sufficient_for_phase": True,
        }
    )
    err = validate_next_step(
        NextStep(
            kind=NextStepKind.CALL_AGENT,
            rationale="r",
            agent_slug="analyst",
            phase_id="phase-1",
        ),
        allowed_agents=["analyst"],
        runtime_state=state,
    )
    assert err == "call_agent step blocked: previous successful result for this phase is already sufficient"


def test_validator_blocks_repeated_pending_question_from_iteration_results():
    mem = _memory()
    state = ensure_runtime_turn_state(mem)
    state.add_iteration_result(
        {
            "iteration": 1,
            "step_kind": NextStepKind.CLARIFY.value,
            "phase_id": "phase-1",
            "outcome": "needs_input",
            "summary": "Нужно уточнение",
            "question": "Уточните период отчета",
            "sufficient_for_phase": False,
        }
    )
    err = validate_next_step(
        NextStep(
            kind=NextStepKind.ASK_USER,
            rationale="r",
            question="  Уточните   период отчета  ",
        ),
        allowed_agents=["analyst"],
        runtime_state=state,
    )
    assert err == "ask_user step repeats pending question from previous iteration"


def test_agent_executor_helper_paths():
    outer = [{"role": "system", "content": "x"}, {"role": "user", "content": "old"}]
    step = NextStep(kind=NextStepKind.CALL_AGENT, rationale="r", agent_slug="ops", agent_input={"query": "new"})
    messages = AgentExecutor._build_sub_messages(outer, step, _memory())  # noqa: SLF001
    assert messages[-1] == {"role": "user", "content": "new"}
    assert all(m["role"] != "system" for m in messages)

    facts = AgentExecutor._extract_facts(  # noqa: SLF001
        "  * first useful line\nshort\nsecond useful line",
        [{"title": "Source A"}],
    )
    assert "first useful line" in facts[0]
    assert any(f.startswith("source: Source A") for f in facts)

@pytest.mark.asyncio
async def test_agent_executor_fast_fallback_when_no_operations():
    executor = AgentExecutor(session=AsyncMock(), llm_client=AsyncMock())
    user_id = uuid4()
    tenant_id = uuid4()
    chat_id = uuid4()
    mem = _memory()
    step = NextStep(kind=NextStepKind.CALL_AGENT, rationale="r", agent_slug="ops", agent_input={"query": "q"})

    executor.preflight.prepare = AsyncMock(
        return_value=SimpleNamespace(
            mode=ExecutionMode.PARTIAL,
            execution_graph={},
            resolved_operations=[],
            resolved_data_instances=[],
            rbac_audit=None,
            agent_slug="ops",
            agent_version=None,
            prompt="",
            agent=SimpleNamespace(model=None),
        )
    )

    async def _should_not_run(**_kwargs):
        raise AssertionError("tool runtime should not be called when no operations are available")

    executor._tool_runtime.execute = _should_not_run  # noqa: SLF001

    from app.agents.context import ToolContext

    ctx = ToolContext(tenant_id=tenant_id, user_id=user_id, chat_id=chat_id)
    state = ensure_runtime_turn_state(mem)
    events = [
        e
        async for e in executor.execute(
            step=step,
            runtime_state=state,
            messages=[{"role": "user", "content": "hello"}],
            ctx=ctx,
            user_id=user_id,
            tenant_id=tenant_id,
            platform_config={},
            model=None,
        )
    ]

    assert any(e.type == RuntimeEventType.STATUS and e.data.get("stage") == "sub_agent_no_operations" for e in events)
    assert state.agent_results
    assert state.agent_results[-1].get("error") == "sub_agent_no_operations"
    deps = ctx.get_runtime_deps()
    assert deps.operation_executor is not None
    assert deps.execution_graph == {}


def test_agent_executor_build_sub_messages_is_bounded_and_trimmed():
    outer = [{"role": "system", "content": "ignore"}]
    for i in range(20):
        outer.append({"role": "assistant" if i % 2 else "user", "content": "x" * 5000})
    step = NextStep(kind=NextStepKind.CALL_AGENT, rationale="r", agent_slug="ops", agent_input={"query": "focused"})
    messages = AgentExecutor._build_sub_messages(outer, step, _memory())  # noqa: SLF001

    # Last message is always planner-focused user query.
    assert messages[-1] == {"role": "user", "content": "focused"}
    # Bounded context before the final query.
    assert len(messages) <= 7
    # Historical message contents are trimmed for token control.
    assert all(len(m.get("content", "")) <= 600 for m in messages[:-1])


def test_planner_llm_output_coerces_agent_input_json_string():
    out = PlannerLLMOutput(
        kind="call_agent",
        rationale="r",
        agent_slug="analyst",
        agent_input='{"query":"tickets","phase_id":"p1"}',
    )
    assert out.agent_input == {"query": "tickets", "phase_id": "p1"}


def test_planning_stage_detects_non_retryable_agent_failure():
    state = ensure_runtime_turn_state(_memory())
    state.add_iteration_result(
        {
            "iteration": 1,
            "step_kind": NextStepKind.CALL_AGENT.value,
            "agent_slug": "mon.net",
            "summary": "request too large",
            "outcome": "failed",
            "retryable": False,
            "error_code": RuntimeErrorCode.AGENT_WALL_TIME_EXCEEDED.value,
            "sufficient_for_phase": False,
        }
    )
    assert classify_agent_failure(state, agent_slug="mon.net")["non_retryable"] is True


def test_planning_stage_detects_non_retryable_auth_failure():
    state = ensure_runtime_turn_state(_memory())
    state.add_iteration_result(
        {
            "iteration": 1,
            "step_kind": NextStepKind.CALL_AGENT.value,
            "agent_slug": "mon.net",
            "summary": "invalid_api_key",
            "outcome": "failed",
            "retryable": False,
            "error_code": RuntimeErrorCode.AGENT_RUNTIME_EXCEPTION.value,
            "sufficient_for_phase": False,
        }
    )
    assert classify_agent_failure(state, agent_slug="mon.net")["non_retryable"] is True


def test_planning_stage_detects_non_retryable_tool_protocol_failure():
    state = ensure_runtime_turn_state(_memory())
    state.add_iteration_result(
        {
            "iteration": 1,
            "step_kind": NextStepKind.CALL_AGENT.value,
            "agent_slug": "mon.net",
            "summary": "tool_use_failed",
            "outcome": "failed",
            "retryable": False,
            "error_code": RuntimeErrorCode.AGENT_NON_RETRYABLE_OPERATION_FAILURE.value,
            "sufficient_for_phase": False,
        }
    )
    assert classify_agent_failure(state, agent_slug="mon.net")["non_retryable"] is True


def test_planning_stage_detects_non_retryable_not_found_failure():
    state = ensure_runtime_turn_state(_memory())
    state.add_iteration_result(
        {
            "iteration": 1,
            "step_kind": NextStepKind.CALL_AGENT.value,
            "agent_slug": "net.enginer",
            "summary": "operation not found",
            "outcome": "failed",
            "retryable": False,
            "error_code": RuntimeErrorCode.OPERATION_UNAVAILABLE.value,
            "sufficient_for_phase": False,
        }
    )
    assert classify_agent_failure(state, agent_slug="net.enginer")["non_retryable"] is True


def test_planning_stage_marks_last_result_as_unavailable_for_preflight_failure():
    state = ensure_runtime_turn_state(_memory())
    state.add_iteration_result(
        {
            "iteration": 1,
            "step_kind": NextStepKind.CALL_AGENT.value,
            "agent_slug": "ops",
            "summary": "sub_agent_unavailable",
            "outcome": "failed",
            "error_code": RuntimeErrorCode.AGENT_PRECHECK_FAILED.value,
            "retryable": False,
            "sufficient_for_phase": False,
        }
    )
    assert classify_agent_failure(state, agent_slug="ops")["unavailable"] is True


def test_planning_stage_remove_agent_by_slug():
    agents = [
        {"slug": "ops", "description": "ops"},
        {"slug": "net", "description": "net"},
    ]
    removed = PlannerCallAgentDispatcher._remove_agent(agents, "ops")  # noqa: SLF001
    assert removed is True
    assert agents == [{"slug": "net", "description": "net"}]


def test_llm_adapter_coerces_tool_choice_mismatch_into_tool_call_block():
    err = RuntimeError(
        "Error code: 400 - {'error': {'message': 'Tool choice is none, but model called a tool', "
        "'type': 'invalid_request_error', 'code': 'tool_use_failed', "
        "'failed_generation': '{\"name\": \"collection.info\", "
        "\"arguments\": {\"collection_slug\": \"ticket_network\", \"limit_per_dimension\": 10}}'}}"
    )
    block = LLMAdapter._coerce_tool_choice_error_to_tool_call(err)  # noqa: SLF001
    assert block is not None
    assert "```tool_call" in block
    assert '"tool": "collection.info"' in block
    assert '"collection_slug": "ticket_network"' in block


def test_llm_adapter_does_not_coerce_regular_errors():
    err = RuntimeError("Error code: 500 - Internal server error")
    block = LLMAdapter._coerce_tool_choice_error_to_tool_call(err)  # noqa: SLF001
    assert block is None


@pytest.mark.asyncio
async def test_planner_retry_and_fallback_paths():
    planner = Planner(session=AsyncMock(), llm_client=AsyncMock())

    planner.llm.invoke = AsyncMock(
        side_effect=[
            SimpleNamespace(
                value=PlannerLLMOutput(
                    kind="call_agent",
                    rationale="first",
                    agent_slug="forbidden",
                    agent_input={},
                ),
                model="test-model",
                request_messages=[],
                raw_response="",
                duration_ms=1,
            ),
            SimpleNamespace(
                value=PlannerLLMOutput(
                    kind="call_agent",
                    rationale="second",
                    agent_slug="analyst",
                    agent_input={"query": "q"},
                ),
                model="test-model",
                request_messages=[],
                raw_response="",
                duration_ms=1,
            ),
        ]
    )

    mem_retry = _memory()
    step, _ = await planner.next_step(
        runtime_state=ensure_runtime_turn_state(mem_retry),
        available_agents=[{"slug": "analyst", "description": "A"}],
    )
    assert step.kind == NextStepKind.CALL_AGENT
    assert step.agent_slug == "analyst"

    planner.llm.invoke = AsyncMock(side_effect=StructuredCallError("llm down"))
    mem_fallback = _memory()
    fallback, _ = await planner.next_step(
        runtime_state=ensure_runtime_turn_state(mem_fallback),
        available_agents=[],
    )
    assert fallback.kind == NextStepKind.ABORT


@pytest.mark.asyncio
async def test_planner_emits_final_kind_when_llm_returns_one():
    """Current wiring: planner's LLM final payload -> FINAL NextStep."""
    planner = Planner(session=AsyncMock(), llm_client=AsyncMock())
    planner.llm.invoke = AsyncMock(
        return_value=SimpleNamespace(
            value=PlannerLLMOutput(
                kind="final",
                rationale="small-talk",
                final_answer="Привет! Чем могу помочь?",
            ),
            model="test-model",
            request_messages=[],
            raw_response="",
            duration_ms=1,
        )
    )

    mem_direct = _memory()
    step, _ = await planner.next_step(
        runtime_state=ensure_runtime_turn_state(mem_direct),
        available_agents=[],
    )
    assert step.kind == NextStepKind.FINAL
    assert step.final_answer == "Привет! Чем могу помочь?"


@pytest.mark.asyncio
async def test_planner_thinking_mode_adds_deliberation_trace_before_decision():
    planner = Planner(session=AsyncMock(), llm_client=AsyncMock())
    planner.llm.invoke = AsyncMock(
        side_effect=[
            SimpleNamespace(
                value=SimpleNamespace(
                    hypotheses=[
                        SimpleNamespace(summary="Use analyst", expected_outcome="Get facts", risks=["latency"], fit="Best for current need"),
                        SimpleNamespace(summary="Ask clarify question", expected_outcome="Reduce ambiguity", risks=["extra turn"], fit="Safer if scope unclear"),
                    ],
                    selected_hypothesis_index=0,
                    selected_action_kind="call_agent",
                    selected_action_summary="Delegate to analyst first",
                    selection_rationale="Facts are missing but agent is available",
                ),
                model="planner-thinking-model",
                request_messages=[],
                raw_response='{"thinking":true}',
                duration_ms=2,
            ),
            SimpleNamespace(
                value=PlannerLLMOutput(
                    kind="call_agent",
                    rationale="Use analyst",
                    agent_slug="analyst",
                    agent_input={"query": "q"},
                ),
                model="planner-model",
                request_messages=[],
                raw_response='{"kind":"call_agent"}',
                duration_ms=1,
            ),
        ]
    )

    state = ensure_runtime_turn_state(_memory())
    state.execution_mode = RuntimeExecutionMode.THINKING

    step, traces = await planner.next_step(
        runtime_state=state,
        available_agents=[{"slug": "analyst", "description": "A"}],
    )

    assert step.kind == NextStepKind.CALL_AGENT
    assert len(traces) == 2
    assert traces[0].step_kind == "thinking"
    assert traces[0].parsed_response["selected_action_kind"] == "call_agent"
    assert traces[1].step_kind == "decision"


@pytest.mark.asyncio
async def test_agent_tool_runtime_fail_fast_on_invalid_operation_call(monkeypatch):
    runtime = AgentToolRuntime(llm_client=AsyncMock())
    run_session = _FakeRunSession()
    runtime._create_run_session = lambda **_kwargs: run_session  # noqa: SLF001
    runtime.logging_resolver.resolve_logging_level = AsyncMock(return_value=SimpleNamespace(value="brief"))
    runtime.prompt_assembler.assemble = lambda *_args, **_kwargs: SimpleNamespace(system_prompt="sys")
    runtime.config_resolver.resolve = AsyncMock(
        return_value=(
            SimpleNamespace(
                max_steps=5,
                max_tool_calls_total=5,
                max_wall_time_ms=10_000,
                tool_timeout_ms=1_000,
                max_retries=0,
            ),
            SimpleNamespace(model="test-model", temperature=0.0, max_tokens=256),
            {"fail_fast_invalid_operation_calls": True},
        )
    )
    runtime.llm.call = AsyncMock(return_value="llm raw")
    runtime.tools.execute = AsyncMock(return_value=(ToolResult.fail("Operation 'list_docs' not found"), []))

    parsed = SimpleNamespace(
        has_tool_calls=True,
        tool_calls=[ToolCall(id="1", tool_name="list_docs", arguments={})],
        text="",
    )
    monkeypatch.setattr("app.agents.runtime.agent.parse_llm_response", lambda *_args, **_kwargs: parsed)

    exec_request = SimpleNamespace(
        agent=SimpleNamespace(slug="ops", logging_level=None),
        resolved_operations=[SimpleNamespace(operation_slug="docs.search", operation="docs.search", scope="collection")],
        resolved_data_instances=[],
        run_id=uuid4(),
        partial_mode_warning=None,
    )
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4(), chat_id=uuid4())
    events = [
        e
        async for e in runtime.execute(
            exec_request=exec_request,
            messages=[{"role": "user", "content": "find docs"}],
            ctx=ctx,
            model=None,
            enable_logging=True,
        )
    ]

    assert any(e.type == RuntimeEventType.ERROR for e in events)
    assert any("unavailable operation" in str(e.data.get("error", "")).lower() for e in events if e.type == RuntimeEventType.ERROR)
    error_events = [e for e in events if e.type == RuntimeEventType.ERROR]
    assert error_events
    assert error_events[0].data.get("error_code") == RuntimeErrorCode.OPERATION_UNAVAILABLE.value
    assert error_events[0].data.get("retryable") is False
    assert run_session.finished is not None
    assert run_session.finished[0] == "failed"
    assert runtime.llm.call.await_count == 1
    assert runtime.tools.execute.await_count == 0


@pytest.mark.asyncio
async def test_agent_tool_runtime_early_stop_when_skipping_required_operation_calls(monkeypatch):
    runtime = AgentToolRuntime(llm_client=AsyncMock())
    run_session = _FakeRunSession()
    runtime._create_run_session = lambda **_kwargs: run_session  # noqa: SLF001
    runtime.logging_resolver.resolve_logging_level = AsyncMock(return_value=SimpleNamespace(value="brief"))
    runtime.prompt_assembler.assemble = lambda *_args, **_kwargs: SimpleNamespace(system_prompt="sys")
    runtime.config_resolver.resolve = AsyncMock(
        return_value=(
            SimpleNamespace(
                max_steps=6,
                max_tool_calls_total=5,
                max_wall_time_ms=10_000,
                tool_timeout_ms=1_000,
                max_retries=0,
            ),
            SimpleNamespace(model="test-model", temperature=0.0, max_tokens=256),
            {"max_steps_without_successful_tool_result": 2},
        )
    )
    runtime.llm.call = AsyncMock(return_value="llm raw")

    parsed = SimpleNamespace(
        has_tool_calls=False,
        tool_calls=[],
        text="answer without tools",
    )
    monkeypatch.setattr("app.agents.runtime.agent.parse_llm_response", lambda *_args, **_kwargs: parsed)

    exec_request = SimpleNamespace(
        agent=SimpleNamespace(slug="ops", logging_level=None),
        resolved_operations=[SimpleNamespace(operation_slug="docs.search", operation="docs.search", scope="collection")],
        resolved_data_instances=[],
        run_id=uuid4(),
        partial_mode_warning=None,
    )
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4(), chat_id=uuid4())
    events = [
        e
        async for e in runtime.execute(
            exec_request=exec_request,
            messages=[{"role": "user", "content": "find docs"}],
            ctx=ctx,
            model=None,
            enable_logging=True,
        )
    ]

    assert any(e.type == RuntimeEventType.ERROR for e in events)
    assert any("skipped required operation calls" in str(e.data.get("error", "")).lower() for e in events if e.type == RuntimeEventType.ERROR)
    assert run_session.finished is not None
    assert run_session.finished[0] == "failed"
    assert runtime.llm.call.await_count == 2


@pytest.mark.asyncio
async def test_agent_tool_runtime_respects_shared_budget_tool_call_limit(monkeypatch):
    runtime = AgentToolRuntime(llm_client=AsyncMock())
    run_session = _FakeRunSession()
    runtime._create_run_session = lambda **_kwargs: run_session  # noqa: SLF001
    runtime.logging_resolver.resolve_logging_level = AsyncMock(return_value=SimpleNamespace(value="brief"))
    runtime.prompt_assembler.assemble = lambda *_args, **_kwargs: SimpleNamespace(system_prompt="sys")
    runtime.config_resolver.resolve = AsyncMock(
        return_value=(
            SimpleNamespace(
                max_steps=3,
                max_tool_calls_total=5,
                max_wall_time_ms=10_000,
                tool_timeout_ms=1_000,
                max_retries=0,
            ),
            SimpleNamespace(model="test-model", temperature=0.0, max_tokens=256),
            {},
        )
    )
    runtime.llm.call = AsyncMock(return_value="llm raw")
    runtime.tools.execute = AsyncMock(return_value=(ToolResult.ok({"ok": True}), []))

    parsed = SimpleNamespace(
        has_tool_calls=True,
        tool_calls=[
            ToolCall(id="1", tool_name="docs.search", arguments={"q": "a"}),
            ToolCall(id="2", tool_name="docs.search", arguments={"q": "b"}),
        ],
        text="",
    )
    monkeypatch.setattr("app.agents.runtime.agent.parse_llm_response", lambda *_args, **_kwargs: parsed)

    exec_request = SimpleNamespace(
        agent=SimpleNamespace(slug="ops", logging_level=None),
        resolved_operations=[SimpleNamespace(operation_slug="docs.search", operation="docs.search", scope="collection")],
        resolved_data_instances=[],
        run_id=uuid4(),
        partial_mode_warning=None,
    )
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4(), chat_id=uuid4())
    ctx.extra["runtime_budget_ledger"] = RunBudgetLedger(
        limits=BudgetLimitsResolver.resolve_from_platform(
            planner_max_steps=10,
            planner_max_wall_time_ms=120_000,
            platform_config={
                "runtime_budget": {
                    "max_planner_iterations": 10,
                    "max_agent_steps": 10,
                    "max_tool_calls_total": 2,
                    "max_wall_time_ms": 120_000,
                    "per_tool_timeout_ms": 30_000,
                    "max_steps_without_success": 2,
                }
            },
        ).run
    )
    events = [
        e
        async for e in runtime.execute(
            exec_request=exec_request,
            messages=[{"role": "user", "content": "find docs"}],
            ctx=ctx,
            model=None,
            enable_logging=True,
        )
    ]

    assert any(e.type == RuntimeEventType.ERROR for e in events)
    err = [e for e in events if e.type == RuntimeEventType.ERROR][-1]
    assert err.data.get("error_code") == RuntimeErrorCode.AGENT_MAX_TOOL_CALLS_EXCEEDED.value


@pytest.mark.asyncio
async def test_agent_tool_runtime_reused_call_does_not_consume_shared_budget(monkeypatch):
    runtime = AgentToolRuntime(llm_client=AsyncMock())
    run_session = _FakeRunSession()
    runtime._create_run_session = lambda **_kwargs: run_session  # noqa: SLF001
    runtime.logging_resolver.resolve_logging_level = AsyncMock(return_value=SimpleNamespace(value="brief"))
    runtime.prompt_assembler.assemble = lambda *_args, **_kwargs: SimpleNamespace(system_prompt="sys")
    runtime.config_resolver.resolve = AsyncMock(
        return_value=(
            SimpleNamespace(
                max_steps=1,
                max_tool_calls_total=5,
                max_wall_time_ms=10_000,
                tool_timeout_ms=1_000,
                max_retries=0,
            ),
            SimpleNamespace(model="test-model", temperature=0.0, max_tokens=256),
            {},
        )
    )
    runtime.llm.call = AsyncMock(return_value="llm raw")

    async def _no_synth(*_args, **_kwargs):
        if False:
            yield None
        return

    runtime._synthesize_answer = _no_synth  # noqa: SLF001

    parsed = SimpleNamespace(
        has_tool_calls=True,
        tool_calls=[
            ToolCall(id="1", tool_name="docs.search", arguments={"q": "dup"}),
            ToolCall(id="2", tool_name="docs.search", arguments={"q": "dup"}),
        ],
        text="",
    )
    monkeypatch.setattr("app.agents.runtime.agent.parse_llm_response", lambda *_args, **_kwargs: parsed)

    class _FakeLedger:
        def __init__(self) -> None:
            self.calls = 0

        def find_successful_result(self, **_kwargs):
            self.calls += 1
            return {"ok": True} if self.calls > 1 else None

    runtime.tools.execute = AsyncMock(
        side_effect=[
            (ToolResult.ok({"ok": True}), []),
            (ToolResult.ok({"ok": True}, reused=True, reused_from_call_id="1"), []),
        ]
    )

    exec_request = SimpleNamespace(
        agent=SimpleNamespace(slug="ops", logging_level=None),
        resolved_operations=[SimpleNamespace(operation_slug="docs.search", operation="docs.search", scope="collection")],
        resolved_data_instances=[],
        run_id=uuid4(),
        partial_mode_warning=None,
    )
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4(), chat_id=uuid4())
    ctx.extra["runtime_tool_ledger"] = _FakeLedger()
    ctx.extra["runtime_tool_reuse_enabled"] = True
    ctx.extra["runtime_budget_ledger"] = RunBudgetLedger(
        limits=BudgetLimitsResolver.resolve_from_platform(
            planner_max_steps=10,
            planner_max_wall_time_ms=120_000,
            platform_config={
                "runtime_budget": {
                    "max_planner_iterations": 10,
                    "max_agent_steps": 10,
                    "max_tool_calls_total": 2,
                    "max_wall_time_ms": 120_000,
                    "per_tool_timeout_ms": 30_000,
                    "max_steps_without_success": 2,
                }
            },
        ).run
    )
    events = [
        e
        async for e in runtime.execute(
            exec_request=exec_request,
            messages=[{"role": "user", "content": "find docs"}],
            ctx=ctx,
            model=None,
            enable_logging=True,
        )
    ]

    assert not [e for e in events if e.type == RuntimeEventType.ERROR]
    op_results = [e for e in events if e.type == RuntimeEventType.TOOL_RESULT]
    assert len(op_results) == 2
    assert bool(op_results[-1].data.get("reused")) is True
    assert any(e.type == RuntimeEventType.BUDGET_SNAPSHOT for e in events)


@pytest.mark.asyncio
async def test_agent_tool_runtime_emits_operation_result_envelope(monkeypatch):
    runtime = AgentToolRuntime(llm_client=AsyncMock())
    run_session = _FakeRunSession()
    runtime._create_run_session = lambda **_kwargs: run_session  # noqa: SLF001
    runtime.logging_resolver.resolve_logging_level = AsyncMock(return_value=SimpleNamespace(value="brief"))
    runtime.prompt_assembler.assemble = lambda *_args, **_kwargs: SimpleNamespace(system_prompt="sys")
    runtime.config_resolver.resolve = AsyncMock(
        return_value=(
            SimpleNamespace(
                max_steps=3,
                max_tool_calls_total=5,
                max_wall_time_ms=10_000,
                tool_timeout_ms=1_000,
                max_retries=0,
            ),
            SimpleNamespace(model="test-model", temperature=0.0, max_tokens=256),
            {"max_steps_without_successful_tool_result": 1},
        )
    )
    runtime.llm.call = AsyncMock(return_value="llm raw")
    runtime.tools.execute = AsyncMock(
        return_value=(
            ToolResult.fail(
                "op unavailable",
                error_code=RuntimeErrorCode.OPERATION_UNAVAILABLE.value,
                retryable=False,
            ),
            [],
        )
    )

    parsed = SimpleNamespace(
        has_tool_calls=True,
        tool_calls=[ToolCall(id="1", tool_name="docs.search", arguments={})],
        text="",
    )
    monkeypatch.setattr("app.agents.runtime.agent.parse_llm_response", lambda *_args, **_kwargs: parsed)

    exec_request = SimpleNamespace(
        agent=SimpleNamespace(slug="ops", logging_level=None),
        resolved_operations=[SimpleNamespace(operation_slug="docs.search", operation="docs.search", scope="collection")],
        resolved_data_instances=[],
        run_id=uuid4(),
        partial_mode_warning=None,
    )
    ctx = ToolContext(tenant_id=uuid4(), user_id=uuid4(), chat_id=uuid4())
    events = [
        e
        async for e in runtime.execute(
            exec_request=exec_request,
            messages=[{"role": "user", "content": "find docs"}],
            ctx=ctx,
            model=None,
            enable_logging=True,
        )
    ]

    op_results = [e for e in events if e.type == RuntimeEventType.TOOL_RESULT]
    assert op_results
    payload = op_results[0].data
    assert payload.get("error_code") == RuntimeErrorCode.OPERATION_UNAVAILABLE.value
    assert payload.get("retryable") is False
    assert isinstance(payload.get("result"), dict)
    assert payload["result"].get("error_code") == RuntimeErrorCode.OPERATION_UNAVAILABLE.value
