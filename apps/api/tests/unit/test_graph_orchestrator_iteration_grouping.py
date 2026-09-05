from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.runtime.orchestrator import GraphOrchestrator
from app.runtime.orchestrator_contracts import AgentExecutionCompletion, AgentExecutionResult, TaskOutcome
from app.runtime.events import RuntimeEvent


class FakeStore:
    def __init__(self) -> None:
        self.plan_id = uuid4()
        self.root_run_id = uuid4()
        self.tasks = [
            SimpleNamespace(task_id="collect", kind="agent", executor="viewer", intent="Collect", instructions="Collect data", inputs={}, expected_outputs=[], checkpoint={}, attempts=1),
            SimpleNamespace(task_id="review", kind="agent", executor="reviewer", intent="Review", instructions="Review data", inputs={}, expected_outputs=[], checkpoint={}, attempts=1),
            SimpleNamespace(task_id="synthesize", kind="synthesis", executor=None, intent="Answer user", instructions="Answer from reports", inputs={}, expected_outputs=[], checkpoint={}, attempts=1),
        ]
        self.completed: set[str] = set()

    async def snapshot(self, plan_id):
        assert plan_id == self.plan_id
        task_data = {
            "collect": {"task_id": "collect", "kind": "agent", "planned_order": 0, "intent": "Collect", "instructions": "Collect data", "status": "completed" if "collect" in self.completed else "ready", "inputs": {}, "needs": [], "result": {"summary": "collect done", "outputs": {}} if "collect" in self.completed else None},
            "review": {"task_id": "review", "kind": "agent", "planned_order": 1, "intent": "Review", "instructions": "Review data", "status": "completed" if "review" in self.completed else "ready", "inputs": {}, "needs": [], "result": {"summary": "review done", "outputs": {}} if "review" in self.completed else None},
            "synthesize": {"task_id": "synthesize", "kind": "synthesis", "planned_order": 2, "intent": "Answer user", "instructions": "Answer from reports", "status": "completed" if "synthesize" in self.completed else "pending", "inputs": {}, "needs": [], "result": None},
        }
        return {
            "root_run_id": str(self.root_run_id),
            "status": "completed" if len(self.completed) == 3 else "active",
            "tasks": task_data,
            "revision": 1,
            "last_failure": None,
        }

    async def claim_ready(self, plan_id):
        assert plan_id == self.plan_id
        return self.tasks.pop(0) if self.tasks else None

    async def apply_result(self, plan_id, task_id, result):
        assert plan_id == self.plan_id
        assert result.outcome is TaskOutcome.COMPLETED
        self.completed.add(task_id)


class FakeExecutor:
    async def execute_attempt(self, *, request, **kwargs):
        return AgentExecutionResult(
            completion=AgentExecutionCompletion.FULFILLED,
            description=f"{request.task_id} done",
        )


class FakeSynthesizer:
    async def stream(self, *, runtime_state, run_id, **_kwargs):
        runtime_state.final_answer = "final answer"
        yield RuntimeEvent.final("final answer", sources=[], run_id=str(run_id), attachments=[])


class TaskResultCollector:
    def __init__(self) -> None:
        self.results = []
        self.final_answer = None
        self.final_error = None

    def add_task_result(self, result) -> None:
        self.results.append(result)


def test_pending_needs_require_a_declared_output_producer() -> None:
    pending_needs = [{"task_id": "consumer", "key": "regulation_content"}]
    unchanged = {
        "tasks": {
            "consumer": {"depends_on": [], "expected_outputs": []},
        }
    }
    resolved_by_graph = {
        "tasks": {
            "consumer": {"depends_on": ["reader"], "expected_outputs": []},
            "reader": {
                "expected_outputs": [
                    {"key": "regulation_content", "description": "Regulation text"}
                ]
            },
        }
    }

    assert not GraphOrchestrator._has_declared_resolvers(unchanged, pending_needs)
    assert GraphOrchestrator._has_declared_resolvers(resolved_by_graph, pending_needs)


@pytest.mark.asyncio
async def test_groups_ready_tasks_under_one_execution_iteration():
    store = FakeStore()
    orchestrator = GraphOrchestrator(store=store, planner=object(), executor=FakeExecutor(), synthesizer=FakeSynthesizer())

    events = [
        event
        async for event in orchestrator.run(
            plan_id=store.plan_id,
            goal="Test grouping",
            available_agents=[],
            planner_kwargs={"runtime_state": TaskResultCollector()},
        )
    ]

    starts = [event for event in events if event["type"] == "planner_iteration_start"]
    ends = [event for event in events if event["type"] == "planner_iteration_end"]
    step_starts = [event for event in events if event["type"] == "step_start"]

    assert len(starts) == len(ends) == 1
    assert [event["step_number"] for event in step_starts] == [1, 2, 3]
    assert {event["parent_entity_id"] for event in step_starts} == {starts[0]["entity_id"]}


@pytest.mark.asyncio
async def test_completed_task_results_reach_terminal_synthesis_checkpoint():
    store = FakeStore()
    runtime_state = TaskResultCollector()
    orchestrator = GraphOrchestrator(store=store, planner=object(), executor=FakeExecutor(), synthesizer=FakeSynthesizer())

    events = [
        event
        async for event in orchestrator.run(
            plan_id=store.plan_id,
            goal="Complete and synthesize",
            available_agents=[],
            planner_kwargs={"runtime_state": runtime_state},
        )
    ]

    assert [result["task_id"] for result in runtime_state.results] == ["collect", "review"]
    assert [result["outcome"] for result in runtime_state.results] == ["completed", "completed"]
    assert events[-1]["type"] == "plan_terminal"
    assert events[-1]["status"] == "completed"
