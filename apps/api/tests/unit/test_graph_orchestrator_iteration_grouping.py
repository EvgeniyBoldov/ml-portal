from __future__ import annotations

from uuid import uuid4

import pytest

from app.runtime.orchestrator import GraphOrchestrator
from app.runtime.orchestrator_contracts import (
    TaskCompletionDeclaration, TaskExecutionReceipt, IterationProposal,
    PlannedTask, SynthesisBrief, TaskExecutionError, TaskResolution, TerminalKind,
)
from app.runtime.plan_store import InMemoryPlanStore


class AsyncMemoryStore:
    def __init__(self) -> None:
        self.inner = InMemoryPlanStore()
        self.plan = self.inner.create(goal="goal", root_run_id=str(uuid4()), tenant_id="tenant")

    async def snapshot(self, plan_id): return self.inner.snapshot(str(plan_id))
    async def apply_iteration(self, plan_id, proposal, **kwargs): return self.inner.apply_iteration(str(plan_id), proposal, **kwargs)
    async def next_decision(self, plan_id): return self.inner.next_decision(str(plan_id))
    async def claim_task(self, plan_id, task_id): return self.inner.claim_task(str(plan_id), task_id)
    async def claim_checkpoint(self, plan_id, kind): return self.inner.claim_checkpoint(str(plan_id), kind)
    async def task_request(self, plan_id, task_id): return self.inner.task_request(str(plan_id), task_id)
    async def finish_attempt(self, plan_id, task_id, **kwargs): return self.inner.finish_attempt(str(plan_id), task_id, **kwargs)
    async def finish_failure(self, plan_id, task_id, failure, **kwargs): return self.inner.finish_failure(str(plan_id), task_id, failure, **kwargs)
    async def complete_synthesis(self, plan_id): return self.inner.complete_synthesis(str(plan_id))
    async def mark_failed(self, plan_id, code, message): return self.inner.mark_failed(str(plan_id), code, message)
    async def recover_stale_claims(self, plan_id, **kwargs): return self.inner.recover_stale_claims(str(plan_id), **kwargs)
    async def link_attempt_execution(self, plan_id, task_id, agent_execution_id): return self.inner.link_attempt_execution(str(plan_id), task_id, agent_execution_id)


class Planner:
    async def plan(self, *, request, **kwargs):
        return IterationProposal(tasks=[], terminal=TerminalKind.SYNTHESIS, synthesis_brief=SynthesisBrief(user_question="goal", planned_work="none", purpose="answer", answer_requirements="short"))


class Executor:
    async def execute_attempt(self, *, request, **kwargs):
        return TaskExecutionReceipt(declaration=TaskCompletionDeclaration(completion="fulfilled", report="done"), verified={})


class Synthesizer:
    async def stream(self, *, runtime_state, run_id, **kwargs):
        runtime_state.final_answer = "answer"
        from app.runtime.events import RuntimeEvent
        yield RuntimeEvent.final("answer", sources=[], run_id=str(run_id), attachments=[])


class State:
    final_answer = None


@pytest.mark.asyncio
async def test_empty_synthesis_iteration_ends_without_checkpoint_task() -> None:
    store = AsyncMemoryStore()
    events = [event async for event in GraphOrchestrator(store=store, planner=Planner(), executor=Executor(), synthesizer=Synthesizer()).run(plan_id=store.plan["id"], goal="goal", available_agents=[], planner_kwargs={"runtime_state": State()})]
    assert events[-1]["status"] == "completed"
    assert store.inner.get(store.plan["id"])["tasks"] == {}
    trace_iteration_id = events[0]["runtime_event"].data["entity_id"]
    assert store.inner.get(store.plan["id"])["iterations"][0]["id"] == trace_iteration_id


@pytest.mark.asyncio
async def test_task_trace_closes_the_agent_and_step_under_the_persisted_iteration() -> None:
    class TaskPlanner:
        async def plan(self, *, request, **kwargs):
            return IterationProposal(
                tasks=[PlannedTask(
                    task_id="work", executor="research", intent="inspect", instructions="inspect",
                )],
                terminal=TerminalKind.SYNTHESIS,
                synthesis_brief=SynthesisBrief(
                    user_question="goal", planned_work="inspect", purpose="answer", answer_requirements="short",
                ),
            )

    store = AsyncMemoryStore()
    events = [event async for event in GraphOrchestrator(
        store=store, planner=TaskPlanner(), executor=Executor(), synthesizer=Synthesizer(),
    ).run(
        plan_id=store.plan["id"], goal="goal", available_agents=[{"slug": "research"}],
        planner_kwargs={"runtime_state": State()},
    )]
    runtime_events = [event["runtime_event"] for event in events if event.get("type") == "_runtime_event"]
    canonical_events = [event.to_runtime_event() for event in events]
    iteration_id = store.inner.get(store.plan["id"])["iterations"][0]["id"]
    task_planned = next(event for event in canonical_events if event.type.value == "task_planned")
    checkpoint_planned = next(event for event in canonical_events if event.type.value == "checkpoint_planned")
    checkpoint_decided = next(event for event in canonical_events if event.type.value == "checkpoint_decided")
    task_completed_index = next(index for index, event in enumerate(canonical_events) if event.type.value == "task_completed")
    checkpoint_decided_index = canonical_events.index(checkpoint_decided)
    iteration_end_index = next(index for index, event in enumerate(canonical_events) if event.type.value == "planner_iteration_end")
    step_start = next(event for event in runtime_events if event.type.value == "step_start")
    agent_start = next(event for event in runtime_events if event.type.value == "agent_start")
    agent_end = next(event for event in runtime_events if event.type.value == "agent_end")
    step_end = next(event for event in runtime_events if event.type.value == "step_end")

    assert step_start.data["parent_entity_id"] == iteration_id
    assert task_planned.data["parent_entity_id"] == iteration_id
    assert task_planned.data["status"] == "waiting"
    assert checkpoint_decided.data["entity_id"] == checkpoint_planned.data["entity_id"]
    assert checkpoint_planned.data["declared_next"] == "synthesis"
    assert checkpoint_decided.data["effective_next"] == "synthesis"
    assert task_completed_index < checkpoint_decided_index < iteration_end_index
    assert agent_start.data["parent_entity_id"] == step_start.data["entity_id"]
    assert agent_end.data["entity_id"] == agent_start.data["entity_id"]
    assert step_end.data["entity_id"] == step_start.data["entity_id"]


@pytest.mark.asyncio
async def test_iteration_limit_never_creates_a_hidden_finalize_iteration() -> None:
    class ContinuePlanner:
        calls = 0

        async def plan(self, *, request, **kwargs):
            self.calls += 1
            return IterationProposal(tasks=[], terminal=TerminalKind.PLANNER)

    store = AsyncMemoryStore()
    planner = ContinuePlanner()
    events = [event async for event in GraphOrchestrator(
        store=store, planner=planner, executor=Executor(), synthesizer=Synthesizer(),
    ).run(
        plan_id=store.plan["id"], goal="goal", available_agents=[], max_steps=1,
        planner_kwargs={"runtime_state": State()},
    )]

    assert planner.calls == 1
    assert len(store.inner.get(store.plan["id"])["iterations"]) == 1
    assert store.inner.get(store.plan["id"])["last_failure"]["code"] == "iteration_limit_exceeded"
    assert events[-1]["error_code"] == "iteration_limit_exceeded"


@pytest.mark.asyncio
async def test_failed_task_overrides_declared_synthesis_checkpoint_with_planner() -> None:
    class ReplanPlanner:
        calls = 0

        async def plan(self, *, request, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return IterationProposal(
                    tasks=[PlannedTask(
                        task_id="work", executor="research", intent="inspect", instructions="inspect",
                    )],
                    terminal=TerminalKind.SYNTHESIS,
                    synthesis_brief=SynthesisBrief(
                        user_question="goal", planned_work="inspect", purpose="answer", answer_requirements="short",
                    ),
                )
            return IterationProposal(
                tasks=[], terminal=TerminalKind.SYNTHESIS,
                synthesis_brief=SynthesisBrief(
                    user_question="goal", planned_work="inspection failed", purpose="answer", answer_requirements="report limitation",
                ),
                resolutions=[TaskResolution(
                    task_id="work", action="report_unresolved", reason="agent failed",
                )],
            )

    class FailingExecutor:
        async def execute_attempt(self, *, request, **kwargs):
            raise TaskExecutionError("agent failed", code="agent_failed", retryable=False)

    store = AsyncMemoryStore()
    events = [event async for event in GraphOrchestrator(
        store=store, planner=ReplanPlanner(), executor=FailingExecutor(),
        synthesizer=Synthesizer(), max_attempts=1,
    ).run(
        plan_id=store.plan["id"], goal="goal", available_agents=[{"slug": "research"}],
        planner_kwargs={"runtime_state": State()},
    )]
    decisions = [
        event.to_runtime_event()
        for event in events
        if event.get("type") == "checkpoint_decided"
    ]

    assert decisions[0].data["declared_next"] == "synthesis"
    assert decisions[0].data["effective_next"] == "planner"
    assert decisions[0].data["reason"] == "task_failure"
