from uuid import uuid4

import pytest

from app.runtime.llm.structured import StructuredCallError
from app.runtime.orchestrator import GraphOrchestrator


class _Session:
    def __init__(self) -> None:
        self.added: list[object] = []

    def add(self, item: object) -> None:
        self.added.append(item)

    async def flush(self) -> None:
        return None

    async def get(self, _model, _identifier, **_kwargs):
        return self.added[-1] if self.added else None


class _InitialPlanStore:
    def __init__(self) -> None:
        self.plan_id = uuid4()
        self.root_run_id = uuid4()
        self.status = "draft"
        self.failure = None
        self.session = _Session()

    async def snapshot(self, plan_id):
        assert plan_id == self.plan_id
        return {
            "root_run_id": str(self.root_run_id),
            "status": self.status,
            "tasks": {},
            "revision": 0,
            "last_failure": self.failure,
        }

    async def mark_failed(self, plan_id, failure):
        assert plan_id == self.plan_id
        self.status = "failed"
        self.failure = failure


class _InvalidPlanner:
    async def plan(self, **_kwargs):
        raise StructuredCallError("planner returned an invalid graph patch")


class _UnusedExecutor:
    async def execute_task(self, **_kwargs):
        raise AssertionError("task execution must not start after planner failure")


@pytest.mark.asyncio
async def test_initial_planner_failure_closes_trace_and_marks_plan_failed():
    store = _InitialPlanStore()
    observed = []

    async def sink(event):
        observed.append(event)

    orchestrator = GraphOrchestrator(
        store=store,
        planner=_InvalidPlanner(),
        executor=_UnusedExecutor(),
        event_sink=sink,
    )

    events = [
        event
        async for event in orchestrator.run(
            plan_id=store.plan_id,
            goal="Create a request",
            available_agents=[],
        )
    ]

    assert store.status == "failed"
    assert store.failure["code"] == "StructuredCallError"
    assert store.session.added[-1].status == "failed"
    assert [event["type"] for event in events][-4:] == [
        "agent_end",
        "step_end",
        "planner_iteration_end",
        "plan_terminal",
    ]
    assert any(event.type.value == "error" for event in observed)
    assert any(event.type.value == "orchestrator_checkpoint_finished" for event in observed)
