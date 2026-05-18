"""
Tests: lifecycle events (run_start, orchestrator_start/end, planner_iteration_start/end,
agent_start/end, synthesis_start/end) are emitted with correct parent_entity_id linkage.
"""
from __future__ import annotations

from typing import Any, AsyncIterator, List
from uuid import uuid4

import pytest

from app.runtime.contracts import NextStep, NextStepKind, PipelineRequest, PipelineStopReason
from app.runtime.envelope import PhasedEvent
from app.runtime.events import RuntimeEvent, RuntimeEventType
from app.runtime.memory.working_memory import WorkingMemory
from app.runtime.stages.planning_stage import PlanningOutcomeKind, PlanningStage
from app.runtime.turn_state import RuntimeTurnState
from app.agents.context import ToolContext


# ---------------------------------------------------------------------------
# Minimal stubs
# ---------------------------------------------------------------------------

class _PlannerDirect:
    async def next_step(self, **kwargs: Any) -> NextStep:
        return NextStep(
            kind=NextStepKind.DIRECT_ANSWER,
            rationale="direct",
            final_answer="42",
        )


class _PlannerFinal:
    async def next_step(self, **kwargs: Any) -> NextStep:
        return NextStep(
            kind=NextStepKind.FINAL,
            rationale="done",
            final_answer="42",
        )


class _PlannerAbort:
    async def next_step(self, **kwargs: Any) -> NextStep:
        return NextStep(
            kind=NextStepKind.ABORT,
            rationale="cannot help",
        )


class _PlannerAskUser:
    async def next_step(self, **kwargs: Any) -> NextStep:
        return NextStep(
            kind=NextStepKind.ASK_USER,
            rationale="need info",
            question="period?",
        )


class _PlannerCallAgent:
    def __init__(self, agent_slug: str = "ops") -> None:
        self._slug = agent_slug

    async def next_step(self, **kwargs: Any) -> NextStep:
        return NextStep(
            kind=NextStepKind.CALL_AGENT,
            rationale="delegate",
            agent_slug=self._slug,
            agent_input={"query": "q"},
        )


class _AgentNoop:
    """Agent that returns nothing (empty run)."""
    async def execute(self, **kwargs: Any) -> AsyncIterator[RuntimeEvent]:
        if False:
            yield  # type: ignore[misc]
        return


class _AgentWithFinalAnswer:
    """Agent that emits FINAL so planning loop proceeds correctly."""
    async def execute(self, **kwargs: Any) -> AsyncIterator[RuntimeEvent]:
        if False:
            yield  # type: ignore[misc]
        return


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _memory() -> WorkingMemory:
    return WorkingMemory(
        run_id=uuid4(),
        chat_id=uuid4(),
        tenant_id=uuid4(),
        user_id=uuid4(),
        goal="goal",
        question="goal",
        status="running",
    )


def _runtime_state(memory: WorkingMemory) -> RuntimeTurnState:
    return RuntimeTurnState.from_seed(
        run_id=memory.run_id,
        chat_id=memory.chat_id,
        user_id=memory.user_id,
        tenant_id=memory.tenant_id,
        goal=memory.goal,
        current_user_query=memory.question,
        memory_bundle={"sections": [], "diagnostics": {}, "total_budget_used_chars": 0},
    )


def _request(memory: WorkingMemory) -> PipelineRequest:
    return PipelineRequest(
        request_text="goal",
        chat_id=str(memory.chat_id),
        user_id=str(memory.user_id),
        tenant_id=str(memory.tenant_id),
        messages=[],
    )


async def _collect(gen: AsyncIterator[PhasedEvent]) -> List[PhasedEvent]:
    out: List[PhasedEvent] = []
    async for item in gen:
        out.append(item)
    return out


def _types(events: List[PhasedEvent]) -> List[str]:
    return [e.event.type.value for e in events]


def _data(events: List[PhasedEvent], event_type: str) -> List[dict]:
    return [e.event.data for e in events if e.event.type.value == event_type]


# ---------------------------------------------------------------------------
# Tests: RuntimeEvent constructors
# ---------------------------------------------------------------------------

class TestRuntimeEventConstructors:
    def test_run_start(self) -> None:
        run_id = "run-1"
        ev = RuntimeEvent.run_start(run_id=run_id)
        assert ev.type == RuntimeEventType.RUN_START
        assert ev.data["entity_id"] == run_id
        assert ev.data["entity_type"] == "run"

    def test_run_end(self) -> None:
        ev = RuntimeEvent.run_end(run_id="run-1", status="completed")
        assert ev.type == RuntimeEventType.RUN_END
        assert ev.data["status"] == "completed"

    def test_orchestrator_start(self) -> None:
        ev = RuntimeEvent.orchestrator_start(orchestrator_id="orch-1", run_id="run-1", role="planner")
        assert ev.type == RuntimeEventType.ORCHESTRATOR_START
        assert ev.data["entity_id"] == "orch-1"
        assert ev.data["parent_entity_id"] == "run-1"
        assert ev.data["parent_entity_type"] == "run"
        assert ev.data["role"] == "planner"

    def test_orchestrator_end(self) -> None:
        ev = RuntimeEvent.orchestrator_end(orchestrator_id="orch-1", run_id="run-1", status="completed")
        assert ev.type == RuntimeEventType.ORCHESTRATOR_END
        assert ev.data["parent_entity_id"] == "run-1"

    def test_planner_iteration_start(self) -> None:
        ev = RuntimeEvent.planner_iteration_start(
            iteration_id="iter-1", orchestrator_id="orch-1", iteration=1
        )
        assert ev.type == RuntimeEventType.PLANNER_ITERATION_START
        assert ev.data["entity_id"] == "iter-1"
        assert ev.data["parent_entity_id"] == "orch-1"
        assert ev.data["parent_entity_type"] == "orchestrator"
        assert ev.data["iteration"] == 1

    def test_planner_iteration_end(self) -> None:
        ev = RuntimeEvent.planner_iteration_end(
            iteration_id="iter-1", orchestrator_id="orch-1", iteration=1, status="completed"
        )
        assert ev.type == RuntimeEventType.PLANNER_ITERATION_END
        assert ev.data["status"] == "completed"

    def test_agent_start(self) -> None:
        ev = RuntimeEvent.agent_start(
            agent_run_id="agent-run-1",
            parent_entity_id="iter-1",
            agent_slug="ops",
        )
        assert ev.type == RuntimeEventType.AGENT_START
        assert ev.data["entity_id"] == "agent-run-1"
        assert ev.data["parent_entity_id"] == "iter-1"
        assert ev.data["parent_entity_type"] == "planner_iteration"
        assert ev.data["agent_slug"] == "ops"

    def test_agent_end(self) -> None:
        ev = RuntimeEvent.agent_end(
            agent_run_id="agent-run-1",
            parent_entity_id="iter-1",
            agent_slug="ops",
            status="completed",
        )
        assert ev.type == RuntimeEventType.AGENT_END
        assert ev.data["status"] == "completed"

    def test_synthesis_start(self) -> None:
        ev = RuntimeEvent.synthesis_start(synthesis_id="synth-1", run_id="run-1")
        assert ev.type == RuntimeEventType.SYNTHESIS_START
        assert ev.data["entity_id"] == "synth-1"
        assert ev.data["parent_entity_id"] == "run-1"

    def test_synthesis_end(self) -> None:
        ev = RuntimeEvent.synthesis_end(synthesis_id="synth-1", run_id="run-1", status="completed")
        assert ev.type == RuntimeEventType.SYNTHESIS_END
        assert ev.data["status"] == "completed"

    def test_operation_call_carries_parent(self) -> None:
        ev = RuntimeEvent.operation_call(
            operation="search",
            call_id="c1",
            arguments={"q": "x"},
            parent_entity_type="agent_run",
            parent_entity_id="agent-run-1",
            agent_slug="ops",
            agent_run_id="agent-run-1",
            llm_call_id="llm-1",
        )
        assert ev.data["parent_entity_type"] == "agent_run"
        assert ev.data["parent_entity_id"] == "agent-run-1"
        assert ev.data["agent_slug"] == "ops"
        assert ev.data["llm_call_id"] == "llm-1"

    def test_operation_result_carries_parent(self) -> None:
        ev = RuntimeEvent.operation_result(
            operation="search",
            call_id="c1",
            success=True,
            data={},
            parent_entity_type="agent_run",
            parent_entity_id="agent-run-1",
            agent_slug="ops",
            agent_run_id="agent-run-1",
        )
        assert ev.data["parent_entity_type"] == "agent_run"
        assert ev.data["parent_entity_id"] == "agent-run-1"

    def test_error_carries_parent(self) -> None:
        ev = RuntimeEvent.error(
            "boom",
            parent_entity_type="planner_iteration",
            parent_entity_id="iter-1",
        )
        assert ev.data["parent_entity_type"] == "planner_iteration"
        assert ev.data["parent_entity_id"] == "iter-1"


# ---------------------------------------------------------------------------
# Tests: PlanningStage emits lifecycle events
# ---------------------------------------------------------------------------

class TestPlanningStageLifecycle:
    ORCHESTRATOR_ID = "orch-test"

    def _run_stage(
        self,
        planner: Any,
        agent_executor: Any = None,
        max_iterations: int = 3,
    ):
        memory = _memory()
        stage = PlanningStage(
            planner=planner,
            agent_executor=agent_executor or _AgentNoop(),
            max_iterations=max_iterations,
        )
        request = _request(memory)
        state = _runtime_state(memory)
        ctx = ToolContext(tenant_id=memory.tenant_id, user_id=memory.user_id, chat_id=memory.chat_id)
        return stage, state, request, ctx, memory

    @pytest.mark.asyncio
    async def test_direct_answer_emits_iteration_start_end(self) -> None:
        stage, state, request, ctx, memory = self._run_stage(_PlannerDirect())
        events = await _collect(stage.run(
            runtime_state=state, request=request, ctx=ctx,
            user_id=memory.user_id, tenant_id=memory.tenant_id,
            available_agents=[], platform_config={},
            orchestrator_id=self.ORCHESTRATOR_ID,
        ))
        types = _types(events)
        assert "planner_iteration_start" in types
        assert "planner_iteration_end" in types
        # Verify linkage
        start_data = _data(events, "planner_iteration_start")
        assert len(start_data) == 1
        assert start_data[0]["parent_entity_id"] == self.ORCHESTRATOR_ID
        assert start_data[0]["parent_entity_type"] == "orchestrator"
        end_data = _data(events, "planner_iteration_end")
        assert end_data[0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_final_step_emits_iteration_start_end(self) -> None:
        stage, state, request, ctx, memory = self._run_stage(_PlannerFinal())
        events = await _collect(stage.run(
            runtime_state=state, request=request, ctx=ctx,
            user_id=memory.user_id, tenant_id=memory.tenant_id,
            available_agents=[], platform_config={},
            orchestrator_id=self.ORCHESTRATOR_ID,
        ))
        types = _types(events)
        assert "planner_iteration_start" in types
        assert "planner_iteration_end" in types
        end_data = _data(events, "planner_iteration_end")
        assert end_data[0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_abort_emits_iteration_end_with_aborted_status(self) -> None:
        stage, state, request, ctx, memory = self._run_stage(_PlannerAbort())
        events = await _collect(stage.run(
            runtime_state=state, request=request, ctx=ctx,
            user_id=memory.user_id, tenant_id=memory.tenant_id,
            available_agents=[], platform_config={},
            orchestrator_id=self.ORCHESTRATOR_ID,
        ))
        types = _types(events)
        assert "planner_iteration_start" in types
        assert "planner_iteration_end" in types
        end_data = _data(events, "planner_iteration_end")
        assert end_data[0]["status"] == "aborted"
        # error event should carry parent context
        error_data = _data(events, "error")
        assert any(d.get("parent_entity_type") == "planner_iteration" for d in error_data)

    @pytest.mark.asyncio
    async def test_ask_user_emits_iteration_end_with_paused_status(self) -> None:
        stage, state, request, ctx, memory = self._run_stage(_PlannerAskUser())
        events = await _collect(stage.run(
            runtime_state=state, request=request, ctx=ctx,
            user_id=memory.user_id, tenant_id=memory.tenant_id,
            available_agents=[], platform_config={},
            orchestrator_id=self.ORCHESTRATOR_ID,
        ))
        types = _types(events)
        assert "planner_iteration_start" in types
        assert "planner_iteration_end" in types
        end_data = _data(events, "planner_iteration_end")
        assert end_data[0]["status"] == "paused"

    @pytest.mark.asyncio
    async def test_call_agent_emits_agent_start_end(self) -> None:
        stage, state, request, ctx, memory = self._run_stage(
            _PlannerCallAgent(agent_slug="ops"), _AgentWithFinalAnswer(),
        )
        events = await _collect(stage.run(
            runtime_state=state, request=request, ctx=ctx,
            user_id=memory.user_id, tenant_id=memory.tenant_id,
            available_agents=[], platform_config={},
            orchestrator_id=self.ORCHESTRATOR_ID,
        ))
        types = _types(events)
        assert "agent_start" in types
        assert "agent_end" in types

        agent_start_data = _data(events, "agent_start")
        assert len(agent_start_data) >= 1
        assert agent_start_data[0]["agent_slug"] == "ops"
        assert agent_start_data[0]["parent_entity_type"] == "planner_iteration"
        iter_id = agent_start_data[0]["parent_entity_id"]

        agent_end_data = _data(events, "agent_end")
        assert agent_end_data[0]["parent_entity_id"] == iter_id

    @pytest.mark.asyncio
    async def test_iteration_id_parent_links_correctly(self) -> None:
        """Verify that agent_start.parent_entity_id == planner_iteration_start.entity_id."""
        stage, state, request, ctx, memory = self._run_stage(
            _PlannerCallAgent(), _AgentNoop(),
        )
        events = await _collect(stage.run(
            runtime_state=state, request=request, ctx=ctx,
            user_id=memory.user_id, tenant_id=memory.tenant_id,
            available_agents=[], platform_config={},
            orchestrator_id=self.ORCHESTRATOR_ID,
        ))
        iter_start = _data(events, "planner_iteration_start")
        agent_start = _data(events, "agent_start")
        assert len(iter_start) >= 1
        assert len(agent_start) >= 1
        assert agent_start[0]["parent_entity_id"] == iter_start[0]["entity_id"]

    @pytest.mark.asyncio
    async def test_orchestrator_id_propagated_in_iterations(self) -> None:
        """All planner_iteration_start events must carry the passed orchestrator_id."""
        orch_id = f"my-custom-orchestrator-{uuid4()}"
        stage, state, request, ctx, memory = self._run_stage(_PlannerDirect())
        events = await _collect(stage.run(
            runtime_state=state, request=request, ctx=ctx,
            user_id=memory.user_id, tenant_id=memory.tenant_id,
            available_agents=[], platform_config={},
            orchestrator_id=orch_id,
        ))
        for d in _data(events, "planner_iteration_start"):
            assert d["parent_entity_id"] == orch_id

    @pytest.mark.asyncio
    async def test_default_orchestrator_id_when_not_passed(self) -> None:
        """When orchestrator_id is not passed, a default is generated (non-empty)."""
        stage, state, request, ctx, memory = self._run_stage(_PlannerDirect())
        events = await _collect(stage.run(
            runtime_state=state, request=request, ctx=ctx,
            user_id=memory.user_id, tenant_id=memory.tenant_id,
            available_agents=[], platform_config={},
            # No orchestrator_id!
        ))
        for d in _data(events, "planner_iteration_start"):
            assert d["parent_entity_id"]  # must be non-empty string
