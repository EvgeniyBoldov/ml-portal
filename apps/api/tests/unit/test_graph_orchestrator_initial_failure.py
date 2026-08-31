from uuid import uuid4
from types import SimpleNamespace

import pytest

from app.runtime.llm.structured import StructuredCallError
from app.runtime.orchestrator import GraphOrchestrator
from app.runtime.orchestrator_contracts import PlanPatch, PlannerDecisionKind


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
    async def execute_attempt(self, **_kwargs):
        raise AssertionError("task execution must not start after planner failure")


class _SuccessfulInitialPlanStore(_InitialPlanStore):
    def __init__(self) -> None:
        super().__init__()
        self.revision = 0
        self.status = "draft"

    async def snapshot(self, plan_id):
        assert plan_id == self.plan_id
        return {
            "root_run_id": str(self.root_run_id),
            "status": self.status,
            "tasks": {},
            "revision": self.revision,
            "last_failure": self.failure,
        }

    async def apply_patch(self, plan_id, patch, **_kwargs):
        assert plan_id == self.plan_id
        assert patch.expected_revision == self.revision
        self.revision = 7
        self.status = "active"
        return SimpleNamespace(revision=self.revision)

    async def claim_ready(self, _plan_id):
        return None


class _SuccessfulPlanner:
    async def plan(self, **_kwargs):
        return PlanPatch(
            expected_revision=0,
            decision=PlannerDecisionKind.CREATE_PLAN,
        )


class _PendingNeedStore:
    def __init__(self) -> None:
        self.plan_id = uuid4()
        self.root_run_id = uuid4()
        self.status = "active"
        self.revision = 1
        self.failure = None
        self.session = _Session()

    async def snapshot(self, plan_id):
        assert plan_id == self.plan_id
        return {
            "root_run_id": str(self.root_run_id),
            "status": self.status,
            "revision": self.revision,
            "last_failure": self.failure,
            "tasks": {
                "consumer": {
                    "task_id": "consumer",
                    "status": "waiting_dependency",
                    "depends_on": [],
                    "expected_outputs": [],
                    "needs": [{
                        "ref": "source",
                        "key": "source",
                        "description": "Source document",
                        "required": True,
                        "status": "pending",
                    }],
                }
            },
        }

    async def claim_ready(self, _plan_id):
        return None

    async def apply_patch(self, plan_id, patch, **_kwargs):
        assert plan_id == self.plan_id
        assert patch.expected_revision == self.revision
        self.revision += 1
        return SimpleNamespace(revision=self.revision)

    async def mark_failed(self, plan_id, failure):
        assert plan_id == self.plan_id
        self.status = "failed"
        self.failure = failure


class _UnchangedPendingNeedPlanner:
    async def plan(self, *, request, **_kwargs):
        return PlanPatch(
            expected_revision=request.plan["revision"],
            decision=PlannerDecisionKind.REVISE_PLAN,
        )


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


@pytest.mark.asyncio
async def test_initial_planner_records_actual_applied_revision():
    store = _SuccessfulInitialPlanStore()
    observed = []

    async def sink(event):
        observed.append(event)

    orchestrator = GraphOrchestrator(
        store=store,
        planner=_SuccessfulPlanner(),
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

    invocation = store.session.added[-1]
    assert invocation.status == "completed"
    assert invocation.revision_before == 0
    assert invocation.revision_after == 7
    created = next(event for event in events if event["type"] == "plan_created")
    assert created["revision_before"] == 0
    assert created["revision_after"] == 7
    finished = next(event for event in observed if event.type.value == "planner_invocation_finished")
    assert finished.data["revision_after"] == 7


@pytest.mark.asyncio
async def test_pending_need_replan_fails_without_a_producer_or_user_question():
    store = _PendingNeedStore()
    orchestrator = GraphOrchestrator(
        store=store,
        planner=_UnchangedPendingNeedPlanner(),
        executor=_UnusedExecutor(),
    )

    events = [
        event
        async for event in orchestrator.run(
            plan_id=store.plan_id,
            goal="Read source",
            available_agents=[],
        )
    ]

    assert store.status == "failed"
    assert store.failure["code"] == "unresolvable_dependency"
    assert events[-1]["type"] == "plan_terminal"
    assert events[-1]["status"] == "failed"
