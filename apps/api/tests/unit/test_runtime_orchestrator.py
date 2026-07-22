import pytest

from app.runtime.orchestrator import DeterministicOrchestrator
from app.runtime.orchestrator_contracts import AgentTaskResult, TaskOutcome, TaskRequest
from app.runtime.plan_store import InMemoryPlanStore
from app.runtime.planner.simple_planner import SimplePlanner
from app.runtime.events import RuntimeEventType


class SuccessfulExecutor:
    async def execute_task(self, *, request: TaskRequest) -> AgentTaskResult:
        return AgentTaskResult(outcome=TaskOutcome.COMPLETED, outputs={"answer": "ok"})


class TimeoutOnceExecutor:
    def __init__(self):
        self.calls = 0

    async def execute_task(self, *, request: TaskRequest) -> AgentTaskResult:
        self.calls += 1
        if self.calls == 1:
            raise TimeoutError("provider timeout")
        return AgentTaskResult(outcome=TaskOutcome.COMPLETED, outputs={"answer": "ok"})


class DependencyExecutor:
    async def execute_task(self, *, request: TaskRequest) -> AgentTaskResult:
        return AgentTaskResult(
            outcome=TaskOutcome.NEEDS_DEPENDENCY,
            checkpoint={"stage": "partial"},
            needs=[{"key": "source", "kind": "data", "description": "source data"}],
        )


def _plan(store):
    return store.create(goal="goal", root_run_id="run", tenant_id="tenant")


@pytest.mark.asyncio
async def test_orchestrator_executes_initial_plan_and_completes_task():
    store = InMemoryPlanStore()
    plan = _plan(store)
    orchestrator = DeterministicOrchestrator(
        store=store, planner=SimplePlanner(), executor=SuccessfulExecutor()
    )
    events = [event async for event in orchestrator.run(
        plan_id=plan["id"], goal="goal", available_agents=[{"slug": "general"}]
    )]
    assert store.get(plan["id"])["status"] == "completed"
    assert any(event["type"] == "task_result" for event in events)


@pytest.mark.asyncio
async def test_orchestrator_records_retryable_technical_failure_without_fake_result():
    store = InMemoryPlanStore()
    plan = _plan(store)
    orchestrator = DeterministicOrchestrator(
        store=store, planner=SimplePlanner(), executor=TimeoutOnceExecutor(), max_attempts=2
    )
    events = [event async for event in orchestrator.run(
        plan_id=plan["id"], goal="goal", available_agents=[{"slug": "general"}]
    )]
    task = next(iter(store.get(plan["id"])["tasks"].values()))
    assert task["status"] == "waiting_retry"
    assert task["result"] is None
    assert any(event["type"] == "task_attempt_failed" for event in events)


@pytest.mark.asyncio
async def test_orchestrator_persists_checkpoint_for_dependency_result():
    store = InMemoryPlanStore()
    plan = _plan(store)
    orchestrator = DeterministicOrchestrator(
        store=store, planner=SimplePlanner(), executor=DependencyExecutor()
    )
    awaitable = orchestrator.run(
        plan_id=plan["id"], goal="goal", available_agents=[{"slug": "general"}]
    )
    [event async for event in awaitable]
    task = next(iter(store.get(plan["id"])["tasks"].values()))
    assert task["status"] == "waiting_dependency"
    assert task["checkpoint"] == {"stage": "partial"}


def test_orchestrator_event_can_be_adapted_to_canonical_runtime_event():
    from app.runtime.orchestrator import OrchestratorEvent

    event = OrchestratorEvent(type="task_started", task_id="a", plan_id="p")
    runtime_event = event.to_runtime_event()
    assert runtime_event.type is RuntimeEventType.TASK_STARTED
    assert runtime_event.data["task_id"] == "a"
