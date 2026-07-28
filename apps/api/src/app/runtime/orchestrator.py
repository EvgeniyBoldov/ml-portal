"""Deterministic orchestration loop for the canonical plan graph."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Dict, Optional, Protocol

from app.runtime.orchestrator_contracts import (
    AgentTaskResult,
    PlanRequest,
    TaskAttemptFailure,
    TaskOutcome,
    TaskRequest,
)
from app.runtime.plan_store import SqlPlanStore
from uuid import UUID, uuid4
from app.models.runtime_observability import RuntimePlannerInvocation
from app.runtime.events import RuntimeEvent, RuntimeEventType
from app.core.logging import get_logger
from app.runtime.entity_ids import (
    agent_execution_id as make_agent_execution_id,
    attempt_id as make_attempt_id,
    checkpoint_id as make_checkpoint_id,
    planner_iteration_id as make_iteration_id,
    planner_orchestrator_id,
    step_id as make_step_id,
)

logger = get_logger(__name__)


class Planner(Protocol):
    async def plan(self, *, request: PlanRequest, **kwargs: Any): ...


class TaskExecutor(Protocol):
    async def execute_task(self, *, request: TaskRequest) -> AgentTaskResult: ...


class OrchestratorEvent(dict):
    """Small event DTO used by the engine; runtime event adapters can wrap it."""

    def to_runtime_event(self) -> RuntimeEvent:
        event_name = str(self.get("type") or "")
        try:
            event_type = RuntimeEventType(event_name)
        except ValueError:
            return RuntimeEvent.status("orchestrator", **dict(self))
        payload = dict(self)
        payload.pop("type", None)
        if event_type is RuntimeEventType.PLANNER_ITERATION_START:
            return RuntimeEvent.planner_iteration_start(
                iteration_id=str(payload.pop("entity_id")),
                orchestrator_id=str(payload.pop("parent_entity_id")),
                iteration=int(payload.pop("iteration", 0)),
                iteration_type=str(payload.pop("iteration_type", payload.pop("mode", "decision"))),
                **payload,
            )
        if event_type is RuntimeEventType.PLANNER_ITERATION_END:
            return RuntimeEvent.planner_iteration_end(
                iteration_id=str(payload.pop("entity_id")),
                orchestrator_id=str(payload.pop("parent_entity_id")),
                iteration=int(payload.pop("iteration", 0)),
                status=str(payload.pop("status", "completed")),
                iteration_type=str(payload.pop("iteration_type", payload.pop("mode", "decision"))),
                **payload,
            )
        if event_type is RuntimeEventType.AGENT_START:
            return RuntimeEvent.agent_start(
                agent_execution_id=str(payload.pop("agent_execution_id", payload.pop("entity_id"))),
                parent_entity_type=str(payload.pop("parent_entity_type")),
                parent_entity_id=str(payload.pop("parent_entity_id")),
                agent_slug=str(payload.pop("agent_slug")),
                executor_type=str(payload.pop("executor_type", "agent")),
                executor_name=payload.pop("executor_name", None),
                task_title=payload.pop("task_title", None),
                **payload,
            )
        if event_type is RuntimeEventType.AGENT_END:
            return RuntimeEvent.agent_end(
                agent_execution_id=str(payload.pop("agent_execution_id", payload.pop("entity_id"))),
                parent_entity_type=str(payload.pop("parent_entity_type")),
                parent_entity_id=str(payload.pop("parent_entity_id")),
                agent_slug=str(payload.pop("agent_slug")),
                status=str(payload.pop("status", "completed")),
                **payload,
            )
        return RuntimeEvent(event_type, payload)


class GraphOrchestrator:
    """Persisted graph scheduler; all task lifecycle changes go through SQL."""

    def __init__(self, *, store: SqlPlanStore, planner: Planner, executor: TaskExecutor,
                 max_attempts: int = 3, retry_delay_seconds: int = 60,
                 event_sink: Optional[Any] = None,
                 budget_service: Optional[Any] = None,
                 logging_level: str = "brief") -> None:
        self.store, self.planner, self.executor = store, planner, executor
        self.max_attempts = max(1, max_attempts)
        self.retry_delay_seconds = max(1, retry_delay_seconds)
        self.event_sink = event_sink
        self.budget_service = budget_service
        self.logging_level = logging_level

    async def run(self, *, plan_id: UUID, goal: str, available_agents: list[dict[str, Any]],
                  max_steps: int = 80, planner_kwargs: Optional[Dict[str, Any]] = None) -> AsyncIterator[OrchestratorEvent]:
        plan = await self.store.snapshot(plan_id)
        root_run_id = UUID(str(plan["root_run_id"]))
        iteration_number = 1
        orchestrator_id = planner_orchestrator_id(str(root_run_id))

        async def observe(event_type: str, *, entity_type: str, entity_id: str, parent_type: Optional[str] = None, parent_id: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, trigger: Optional[str] = None) -> None:
            # These lifecycle events are yielded below and therefore persisted
            # by RuntimeEventLogger.  All other observations use the same
            # root journal through ``event_sink``.
            if event_type in {"plan_created", "task_started", "task_completed", "task_unfulfillable"}:
                return
            if self.event_sink is None:
                return
            await self.event_sink(RuntimeEvent(
                RuntimeEventType(event_type),
                {
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "parent_entity_type": parent_type,
                    "parent_entity_id": parent_id,
                    "trigger": trigger,
                    **(payload or {}),
                },
            ))
        planner_kwargs = planner_kwargs or {}
        limits = dict(planner_kwargs.get("runtime_limits") or {})
        llm_kwargs = {
            key: planner_kwargs[key]
            for key in ("chat_id", "tenant_id", "user_id", "agent_execution_id", "sandbox_overrides")
            if key in planner_kwargs
        }
        # A planner iteration represents one planner decision and the task
        # steps executed against that decision.  It is deliberately not a
        # synonym for one claimed task.
        active_iteration_id: Optional[str] = None
        active_iteration_type = "execution"
        active_step_number = 1
        iteration_open = False

        def close_active_iteration(*, status: str, outcome: Optional[str] = None) -> Optional[OrchestratorEvent]:
            nonlocal iteration_open
            if not iteration_open or active_iteration_id is None:
                return None
            iteration_open = False
            payload: Dict[str, Any] = {
                "type": "planner_iteration_end",
                "entity_id": active_iteration_id,
                "planner_iteration_id": active_iteration_id,
                "parent_entity_type": "orchestrator",
                "parent_entity_id": orchestrator_id,
                "iteration": iteration_number,
                "iteration_number": iteration_number,
                "iteration_type": active_iteration_type,
                "status": status,
            }
            if outcome:
                payload["outcome"] = outcome
            return OrchestratorEvent(**payload)

        async def revise(*, reason: str, last_failure: Optional[Dict[str, Any]] = None) -> None:
            nonlocal iteration_number, active_iteration_id, active_iteration_type, active_step_number, iteration_open
            current = await self.store.snapshot(plan_id)
            iteration_number += 1
            iteration_entity_id = make_iteration_id(str(root_run_id), iteration_number)
            active_iteration_id = iteration_entity_id
            active_iteration_type = "replan"
            active_step_number = 2
            iteration_open = True
            planner_step_id = make_step_id(iteration_entity_id, 1, "replan")
            planner_executor_id = make_agent_execution_id(iteration_entity_id, "planner", iteration_number)
            invocation_id = uuid4()
            checkpoint_id = make_checkpoint_id(str(root_run_id), "planner", str(invocation_id))
            await observe("orchestrator_checkpoint_started", entity_type="orchestrator_checkpoint", entity_id=checkpoint_id,
                          parent_type="orchestrator", parent_id=orchestrator_id,
                          payload={"kind": "planner", "mode": "replan", "reason": reason, "revision": current["revision"]}, trigger=reason)
            self.store.session.add(RuntimePlannerInvocation(
                id=invocation_id, run_id=root_run_id, orchestrator_id=orchestrator_id,
                plan_id=plan_id, trigger=reason, status="running", revision_before=current["revision"],
                context_snapshot={"goal": goal, "last_failure": last_failure},
            ))
            await self.store.session.flush()
            await observe("planner_invocation_started", entity_type="planner_invocation", entity_id=str(invocation_id), parent_type="orchestrator", parent_id=orchestrator_id, payload={"trigger": reason, "revision": current["revision"]}, trigger=reason)
            await observe("planner_iteration_start", entity_type="planner_iteration", entity_id=iteration_entity_id, parent_type="orchestrator", parent_id=orchestrator_id, payload={"iteration": iteration_number, "iteration_number": iteration_number, "iteration_type": "replan", "mode": "replan"}, trigger=reason)
            await observe("step_start", entity_type="step", entity_id=planner_step_id, parent_type="planner_iteration", parent_id=iteration_entity_id, payload={"step_number": 1, "kind": "plan", "title": "Перепланировать", "objective": reason}, trigger=reason)
            await observe("agent_start", entity_type="agent_execution", entity_id=planner_executor_id, parent_type="step", parent_id=planner_step_id, payload={"agent_execution_id": planner_executor_id, "agent_slug": "planner", "executor_type": "planner", "executor_name": "Планер", "task_title": reason}, trigger=reason)
            patch = await self.planner.plan(request=PlanRequest(
                goal=goal,
                available_agents=available_agents,
                plan=current,
                needs=[
                    {"task_id": task_id, **need}
                    for task_id, task in current.get("tasks", {}).items()
                    for need in task.get("needs", [])
                    if isinstance(need, dict)
                ],
                last_failure=last_failure,
                trigger=reason,
                run_id=root_run_id,
                plan_id=plan_id,
                trace_parent_id=checkpoint_id,
            ), **{**llm_kwargs, "agent_execution_id": UUID(planner_executor_id), "event_sink": self.event_sink})
            decision = await self.budget_service.consume(run_id=root_run_id, owner_type="run", owner_id=str(root_run_id), metric="plan_revisions", limit=limits.get("plan_revisions"), reason=reason) if self.budget_service else None
            if decision is not None and not decision.allowed:
                raise RuntimeError("plan revision budget exceeded")
            updated = await self.store.apply_patch(plan_id, patch, reason=reason, planner_invocation_id=str(invocation_id))
            invocation = await self.store.session.get(RuntimePlannerInvocation, invocation_id, with_for_update=True)
            if invocation:
                invocation.status, invocation.revision_after, invocation.finished_at = "completed", updated.revision, datetime.now(timezone.utc)
            await observe("plan_patch_applied", entity_type="plan", entity_id=str(plan_id), parent_type="orchestrator", parent_id=orchestrator_id, payload={"revision": updated.revision, "patch": patch.model_dump(mode="json")}, trigger=reason)
            await observe("orchestrator_checkpoint_finished", entity_type="orchestrator_checkpoint", entity_id=checkpoint_id,
                          parent_type="orchestrator", parent_id=orchestrator_id,
                          payload={"kind": "planner", "mode": "replan", "status": "completed", "revision": updated.revision}, trigger=reason)
            await observe("agent_end", entity_type="agent_execution", entity_id=planner_executor_id, parent_type="step", parent_id=planner_step_id, payload={"agent_execution_id": planner_executor_id, "agent_slug": "planner", "status": "completed"}, trigger=reason)
            await observe("step_end", entity_type="step", entity_id=planner_step_id, parent_type="planner_iteration", parent_id=iteration_entity_id, payload={"step_number": 1, "status": "completed", "outcome": "success"}, trigger=reason)
        if not plan["tasks"]:
            invocation_id = uuid4()
            checkpoint_id = make_checkpoint_id(str(root_run_id), "planner", str(invocation_id))
            await observe("orchestrator_checkpoint_started", entity_type="orchestrator_checkpoint", entity_id=checkpoint_id,
                          parent_type="orchestrator", parent_id=orchestrator_id,
                          payload={"kind": "planner", "mode": "initial", "revision": plan["revision"]}, trigger="initial")
            self.store.session.add(RuntimePlannerInvocation(
                id=invocation_id, run_id=root_run_id, orchestrator_id=orchestrator_id,
                plan_id=plan_id, trigger="initial", status="running", revision_before=plan["revision"], context_snapshot={"goal": goal},
            ))
            await self.store.session.flush()
            await observe("planner_invocation_started", entity_type="planner_invocation", entity_id=str(invocation_id), parent_type="orchestrator", parent_id=orchestrator_id, payload={"trigger": "initial", "revision": plan["revision"]}, trigger="initial")
            iteration_id = make_iteration_id(str(root_run_id), iteration_number)
            active_iteration_id = iteration_id
            active_iteration_type = "decision"
            active_step_number = 2
            iteration_open = True
            step_id = make_step_id(iteration_id, 1, "plan")
            planner_executor_id = make_agent_execution_id(iteration_id, "planner", 1)
            yield OrchestratorEvent(type="planner_iteration_start", entity_id=iteration_id,
                                    planner_iteration_id=iteration_id, parent_entity_type="orchestrator",
                                    parent_entity_id=orchestrator_id, iteration=iteration_number,
                                    iteration_number=iteration_number, iteration_type="decision", mode="initial")
            yield OrchestratorEvent(type="step_start", entity_id=step_id, entity_type="step",
                                    parent_entity_type="planner_iteration", parent_entity_id=iteration_id,
                                    step_number=1, kind="plan", title="Сформировать план", objective=goal)
            yield OrchestratorEvent(type="agent_start", entity_id=planner_executor_id,
                                    agent_execution_id=planner_executor_id, parent_entity_type="step",
                                    parent_entity_id=step_id, agent_slug="planner", role="planner",
                                    executor_type="planner", executor_name="Планер", task_title=goal)
            patch = await self.planner.plan(request=PlanRequest(
                goal=goal, available_agents=available_agents, plan=plan,
                trigger="initial", run_id=root_run_id, plan_id=plan_id,
                trace_parent_id=iteration_id,
            ), **{**llm_kwargs, "agent_execution_id": UUID(planner_executor_id), "event_sink": self.event_sink})
            await self.store.apply_patch(plan_id, patch, reason="initial_plan")
            invocation = await self.store.session.get(RuntimePlannerInvocation, invocation_id, with_for_update=True)
            if invocation is not None:
                invocation.status = "completed"
                invocation.revision_after = plan["revision"] + 1
                invocation.finished_at = datetime.now(timezone.utc)
            if self.budget_service is not None:
                decision = await self.budget_service.consume(run_id=root_run_id, owner_type="run", owner_id=str(root_run_id), metric="plan_revisions", limit=limits.get("plan_revisions"), reason="initial_plan")
                if not decision.allowed:
                    raise RuntimeError("plan revision budget exceeded")
            await observe("plan_created", entity_type="plan", entity_id=str(plan_id), parent_type="agent_execution", parent_id=planner_executor_id,
                          payload={"revision": 1, "mode": "initial", "patch": patch.model_dump(mode="json")}, trigger="initial")
            await observe("orchestrator_checkpoint_finished", entity_type="orchestrator_checkpoint", entity_id=checkpoint_id,
                          parent_type="orchestrator", parent_id=orchestrator_id,
                          payload={"kind": "planner", "mode": "initial", "status": "completed", "revision": 1}, trigger="initial")
            yield OrchestratorEvent(type="agent_end", entity_id=planner_executor_id,
                                    agent_execution_id=planner_executor_id, parent_entity_type="step",
                                    parent_entity_id=step_id, agent_slug="planner", role="planner", status="completed")
            yield OrchestratorEvent(type="step_end", entity_id=step_id, entity_type="step",
                                    parent_entity_type="planner_iteration", parent_entity_id=iteration_id,
                                    step_number=1, status="completed", outcome="success", summary="План сформирован")
            yield OrchestratorEvent(type="plan_created", entity_type="plan", entity_id=str(plan_id),
                                    parent_entity_type="agent_execution", parent_entity_id=planner_executor_id,
                                    plan_id=str(plan_id), revision=1, mode="initial",
                                    patch=patch.model_dump(mode="json"))
        else:
            # A resumed persisted plan has no new planner call in this run,
            # but its task steps still need one explicit execution iteration.
            active_iteration_id = make_iteration_id(str(root_run_id), iteration_number)
            active_iteration_type = "execution"
            active_step_number = 1
            iteration_open = True
            yield OrchestratorEvent(type="planner_iteration_start", entity_id=active_iteration_id,
                                    planner_iteration_id=active_iteration_id, parent_entity_type="orchestrator",
                                    parent_entity_id=orchestrator_id, iteration=iteration_number,
                                    iteration_number=iteration_number, iteration_type="execution", mode="resume")
        for _ in range(max_steps):
            plan = await self.store.snapshot(plan_id)
            if plan["status"] in {"completed", "waiting_input", "failed", "cancelled"}:
                closed = close_active_iteration(status=plan["status"])
                if closed is not None:
                    yield closed
                yield OrchestratorEvent(type="plan_terminal", plan_id=str(plan_id), status=plan["status"])
                return
            task = await self.store.claim_ready(plan_id)
            if task is None:
                closed = close_active_iteration(status="stalled")
                if closed is not None:
                    yield closed
                yield OrchestratorEvent(type="plan_stalled", plan_id=str(plan_id))
                return
            if active_iteration_id is None:
                raise RuntimeError("task execution requires an active planner iteration")
            task_id = task.task_id
            snapshot = await self.store.snapshot(plan_id)
            dependencies = {
                dep: snapshot["tasks"].get(dep, {}).get("result", {}).get("outputs", {})
                for dep in snapshot["tasks"].get(task_id, {}).get("depends_on", [])
            }
            request = TaskRequest(task_id=task_id, intent=task.intent, instructions=task.instructions,
                                  executor=task.executor, inputs=task.inputs or {},
                                  needs=snapshot["tasks"].get(task_id, {}).get("needs", []),
                                  checkpoint=task.checkpoint or {}, dependency_outputs=dependencies)
            checkpoint_id = make_checkpoint_id(str(root_run_id), "task", f"{task_id}:{task.attempts}")
            executor_id = make_agent_execution_id(active_iteration_id, task_id, task.attempts)
            await observe("orchestrator_checkpoint_started", entity_type="orchestrator_checkpoint", entity_id=checkpoint_id,
                          parent_type="orchestrator", parent_id=orchestrator_id,
                          payload={"kind": "task", "task_id": task_id, "attempt": task.attempts, "executor": task.executor})
            await observe("task_started", entity_type="task", entity_id=task_id, parent_type="plan", parent_id=str(plan_id), payload={"attempt": task.attempts, "checkpoint_id": checkpoint_id})
            attempt_entity_id = make_attempt_id(task_id, task.attempts)
            await observe("attempt_started", entity_type="attempt", entity_id=attempt_entity_id, parent_type="task", parent_id=task_id, payload={"attempt": task.attempts, "attempt_number": task.attempts})
            if self.budget_service is not None:
                decision = await self.budget_service.consume(run_id=root_run_id, owner_type="run", owner_id=str(root_run_id), metric="task_attempts", limit=limits.get("task_attempts"), reason="task_started")
                if not decision.allowed:
                    raise RuntimeError("task attempt budget exceeded")
            yield OrchestratorEvent(type="task_started", entity_type="task", entity_id=task_id,
                                    parent_entity_type="plan", parent_entity_id=str(plan_id),
                                    plan_id=str(plan_id), task_id=task_id, attempt=task.attempts)
            step_number = active_step_number
            step_id = make_step_id(active_iteration_id, step_number, task_id)
            yield OrchestratorEvent(type="step_start", entity_id=step_id, entity_type="step",
                                    parent_entity_type="planner_iteration", parent_entity_id=active_iteration_id,
                                    step_number=step_number, kind="call_agent", title=task.intent, objective=task.instructions,
                                    intent=task.intent, inputs=task.inputs or {})
            yield OrchestratorEvent(type="agent_start", entity_id=executor_id, agent_execution_id=executor_id,
                                    parent_entity_type="step", parent_entity_id=step_id,
                                    agent_slug=task.executor, task_id=task_id, attempt=task.attempts,
                                    task_title=task.intent, task_objective=task.instructions,
                                    executor_type="agent", executor_name=task.executor,
                                    task_inputs=task.inputs or {}, expected_outputs=[
                                        item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                                        for item in (task.expected_outputs or [])
                                    ])
            try:
                task_executor_kwargs = dict(planner_kwargs)
                task_executor_kwargs["runtime_run_id"] = str(root_run_id)
                task_executor_kwargs["lifecycle_agent_execution_id"] = executor_id
                task_executor_kwargs["runtime_log_parent"] = {"entity_type": "step", "entity_id": step_id}
                task_executor_kwargs["iteration_id"] = active_iteration_id
                result = await self.executor.execute_task(request=request, **task_executor_kwargs)
            except Exception as exc:
                failure = TaskAttemptFailure(code=type(exc).__name__, message=str(exc) or "task execution failed", retryable=True)
                await self.store.record_failure(plan_id, task_id, failure,
                    retry_at=datetime.now(timezone.utc) + timedelta(seconds=self.retry_delay_seconds),
                    max_attempts=self.max_attempts)
                await observe("attempt_failed", entity_type="attempt", entity_id=attempt_entity_id, parent_type="task", parent_id=task_id, payload={"error": failure.model_dump(mode="json")}, trigger="technical_failure")
                await observe("orchestrator_checkpoint_finished", entity_type="orchestrator_checkpoint", entity_id=checkpoint_id,
                              parent_type="orchestrator", parent_id=orchestrator_id,
                              payload={"kind": "task", "task_id": task_id, "attempt": task.attempts, "status": "failed_technical", "error": failure.model_dump(mode="json")}, trigger="technical_failure")
                yield OrchestratorEvent(type="agent_end", entity_id=executor_id, agent_execution_id=executor_id,
                                        parent_entity_type="step", parent_entity_id=step_id,
                                        agent_slug=task.executor, task_id=task_id, status="failed",
                                        task_title=task.intent, task_objective=task.instructions)
                yield OrchestratorEvent(type="step_end", entity_id=step_id, entity_type="step",
                                        parent_entity_type="planner_iteration", parent_entity_id=active_iteration_id,
                                        step_number=step_number, status="failed", outcome="technical_failure", summary=failure.message)
                yield OrchestratorEvent(type="task_attempt_failed", plan_id=str(plan_id), task_id=task_id,
                                        error=failure.model_dump(mode="json"))
                active_step_number += 1
                if not failure.retryable or task.attempts >= self.max_attempts:
                    closed = close_active_iteration(status="failed", outcome="technical_failure")
                    if closed is not None:
                        yield closed
                    await revise(reason="technical_failure", last_failure=failure.model_dump(mode="json"))
                continue
            await self.store.apply_result(plan_id, task_id, result)
            result_event = "task_completed" if result.outcome.value == "completed" else "task_unfulfillable" if result.outcome.value == "unfulfillable" else "task_paused"
            await observe(result_event, entity_type="task", entity_id=task_id, parent_type="plan", parent_id=str(plan_id), payload={"outcome": result.outcome.value, "summary": result.summary, "outputs": result.outputs}, trigger=result.outcome.value)
            await observe("attempt_succeeded", entity_type="attempt", entity_id=attempt_entity_id, parent_type="task", parent_id=task_id, payload={"outcome": result.outcome.value, "attempt_number": task.attempts})
            await observe("orchestrator_checkpoint_finished", entity_type="orchestrator_checkpoint", entity_id=checkpoint_id,
                          parent_type="orchestrator", parent_id=orchestrator_id,
                          payload={"kind": "task", "task_id": task_id, "attempt": task.attempts, "status": result.outcome.value, "summary": result.summary}, trigger=result.outcome.value)
            yield OrchestratorEvent(type="agent_end", entity_id=executor_id, agent_execution_id=executor_id,
                                    parent_entity_type="step", parent_entity_id=step_id,
                                    agent_slug=task.executor, task_id=task_id,
                                    task_title=task.intent, task_objective=task.instructions,
                                    summary=result.summary,
                                    outcome=result.outcome.value,
                                    status="completed" if result.outcome.value == "completed" else result.outcome.value)
            yield OrchestratorEvent(type="step_end", entity_id=step_id, entity_type="step",
                                    parent_entity_type="planner_iteration", parent_entity_id=active_iteration_id,
                                    step_number=step_number, status="completed" if result.outcome.value == "completed" else result.outcome.value,
                                    outcome=result.outcome.value, summary=result.summary,
                                    sufficient_for_phase=result.outcome.value == "completed")
            yield OrchestratorEvent(type=("task_completed" if result.outcome.value == "completed" else "task_unfulfillable"),
                                    entity_type="task", entity_id=task_id,
                                    parent_entity_type="plan", parent_entity_id=str(plan_id),
                                    plan_id=str(plan_id), task_id=task_id, outcome=result.outcome.value)
            active_step_number += 1
            if result.outcome in {TaskOutcome.NEEDS_DEPENDENCY, TaskOutcome.UNFULFILLABLE}:
                closed = close_active_iteration(status=result.outcome.value, outcome=result.outcome.value)
                if closed is not None:
                    yield closed
                await revise(reason=result.outcome.value)
        closed = close_active_iteration(status="max_steps")
        if closed is not None:
            yield closed
        yield OrchestratorEvent(type="max_steps", plan_id=str(plan_id))
