from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.runtime.orchestrator import GraphOrchestrator
from app.runtime.orchestrator_contracts import AgentTaskResult, TaskOutcome


class FakeStore:
    def __init__(self) -> None:
        self.plan_id = uuid4()
        self.root_run_id = uuid4()
        self.tasks = [
            SimpleNamespace(task_id="collect", executor="viewer", intent="Collect", instructions="Collect data", inputs={}, expected_outputs=[], checkpoint={}, attempts=1),
            SimpleNamespace(task_id="review", executor="reviewer", intent="Review", instructions="Review data", inputs={}, expected_outputs=[], checkpoint={}, attempts=1),
        ]
        self.completed: set[str] = set()

    async def snapshot(self, plan_id):
        assert plan_id == self.plan_id
        task_data = {
            "collect": {"status": "completed" if "collect" in self.completed else "ready", "inputs": {}, "needs": [], "result": None},
            "review": {"status": "completed" if "review" in self.completed else "ready", "inputs": {}, "needs": [], "result": None},
        }
        return {
            "root_run_id": str(self.root_run_id),
            "status": "completed" if len(self.completed) == 2 else "active",
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
    async def execute_task(self, *, request, **kwargs):
        return AgentTaskResult(outcome=TaskOutcome.COMPLETED, summary=f"{request.task_id} done")


@pytest.mark.asyncio
async def test_groups_ready_tasks_under_one_execution_iteration():
    store = FakeStore()
    orchestrator = GraphOrchestrator(store=store, planner=object(), executor=FakeExecutor())

    events = [
        event
        async for event in orchestrator.run(
            plan_id=store.plan_id,
            goal="Test grouping",
            available_agents=[],
        )
    ]

    starts = [event for event in events if event["type"] == "planner_iteration_start"]
    ends = [event for event in events if event["type"] == "planner_iteration_end"]
    step_starts = [event for event in events if event["type"] == "step_start"]

    assert len(starts) == len(ends) == 1
    assert [event["step_number"] for event in step_starts] == [1, 2]
    assert {event["parent_entity_id"] for event in step_starts} == {starts[0]["entity_id"]}
