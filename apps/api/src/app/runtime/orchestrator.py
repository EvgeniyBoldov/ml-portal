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
from app.runtime.plan_store import InMemoryPlanStore, SqlPlanStore
from uuid import UUID, uuid4
from app.models.runtime_observability import RuntimePlannerInvocation
from app.runtime.events import RuntimeEvent, RuntimeEventType
from app.core.logging import get_logger
from app.services.runtime_observation_writer import RuntimeObservationEvent, RuntimeObservationWriter
from app.services.runtime_budget_service import RuntimeBudgetService

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
        return RuntimeEvent(event_type, payload)


class DeterministicOrchestrator:
    """Executes one task at a time and delegates graph changes to the planner."""

    def __init__(
        self,
        *,
        store: InMemoryPlanStore,
        planner: Planner,
        executor: TaskExecutor,
        max_attempts: int = 3,
        retry_delay_seconds: int = 60,
    ) -> None:
        self.store = store
        self.planner = planner
        self.executor = executor
        self.max_attempts = max(1, max_attempts)
        self.retry_delay_seconds = max(1, retry_delay_seconds)

    async def run(
        self,
        *,
        plan_id: str,
        goal: str,
        available_agents: list[dict[str, Any]],
        max_steps: int = 80,
    ) -> AsyncIterator[OrchestratorEvent]:
        plan = self.store.get(plan_id)
        iteration_number = 0
        if not plan["tasks"]:
            patch = self.planner.create_or_revise(
                request=PlanRequest(goal=goal, available_agents=available_agents, plan=plan)
            )
            self.store.apply_patch(plan_id, patch, reason="initial_plan")
            logger.info("runtime plan created", extra={"plan_id": plan_id, "plan_revision": plan["revision"]})
            yield OrchestratorEvent(type="plan_patch_applied", plan_id=plan_id, revision=plan["revision"])

        for _ in range(max_steps):
            plan = self.store.get(plan_id)
            if plan["status"] in {"completed", "waiting_input", "failed", "cancelled"}:
                yield OrchestratorEvent(type="plan_terminal", plan_id=plan_id, status=plan["status"])
                return
            task = self.store.claim_ready(plan_id)
            if task is None:
                if any(item["status"] == "waiting_retry" for item in plan["tasks"].values()):
                    yield OrchestratorEvent(type="waiting_retry", plan_id=plan_id)
                    return
                if any(item["status"] == "waiting_dependency" for item in plan["tasks"].values()):
                    patch = self.planner.create_or_revise(
                        request=PlanRequest(goal=goal, available_agents=available_agents, plan=plan)
                    )
                    if patch.tasks or patch.question or patch.decision.value in {"ask_user", "complete_plan", "fail_plan"}:
                        self.store.apply_patch(plan_id, patch, reason="dependency_replan")
                        yield OrchestratorEvent(type="plan_patch_applied", plan_id=plan_id, revision=plan["revision"])
                        continue
                self.store._refresh_plan_status(plan_id)  # noqa: SLF001 - store owns the invariant
                yield OrchestratorEvent(type="plan_stalled", plan_id=plan_id)
                return

            request = TaskRequest(
                task_id=task["task_id"],
                title=task["title"],
                objective=task["objective"],
                agent_slug=task["agent_slug"],
                inputs=task.get("inputs", {}),
                checkpoint=task.get("checkpoint", {}),
                dependency_outputs={
                    dependency: plan["tasks"][dependency].get("result", {}).get("outputs", {})
                    for dependency in task.get("depends_on", [])
                },
            )
            yield OrchestratorEvent(type="task_started", plan_id=plan_id, task_id=task["task_id"], attempt=task["attempts"])
            logger.info(
                "runtime task attempt started",
                extra={"plan_id": plan_id, "task_id": task["task_id"], "attempt": task["attempts"], "agent_slug": task["agent_slug"]},
            )
            try:
                result = await self.executor.execute_task(request=request)
            except Exception as exc:  # infrastructure failure, not an agent result
                failure = TaskAttemptFailure(
                    code=type(exc).__name__,
                    message=str(exc) or "task execution failed",
                    retryable=True,
                )
                retry_at = datetime.now(timezone.utc) + timedelta(seconds=self.retry_delay_seconds)
                self.store.record_failure(
                    plan_id,
                    task["task_id"],
                    failure,
                    retry_at=retry_at,
                    max_attempts=self.max_attempts,
                )
                logger.warning(
                    "runtime task attempt failed",
                    extra={"plan_id": plan_id, "task_id": task["task_id"], "attempt": task["attempts"], "error_code": failure.code, "retryable": failure.retryable},
                )
                yield OrchestratorEvent(type="task_attempt_failed", plan_id=plan_id, task_id=task["task_id"], error=failure.model_dump(mode="json"))
                if self.store.get(plan_id)["tasks"][task["task_id"]]["status"] == "failed":
                    patch = self.planner.create_or_revise(
                        request=PlanRequest(
                            goal=goal,
                            available_agents=available_agents,
                            plan=self.store.get(plan_id),
                            last_failure=failure.model_dump(mode="json"),
                        )
                    )
                    if patch.tasks or patch.question or patch.decision.value in {"ask_user", "complete_plan", "fail_plan"}:
                        self.store.apply_patch(plan_id, patch, reason="technical_failure")
                return

            self.store.apply_result(plan_id, task["task_id"], result)
            logger.info(
                "runtime task result applied",
                extra={"plan_id": plan_id, "task_id": task["task_id"], "outcome": result.outcome.value},
            )
            yield OrchestratorEvent(
                type="task_result",
                plan_id=plan_id,
                task_id=task["task_id"],
                outcome=result.outcome.value,
            )
            if result.outcome in {TaskOutcome.NEEDS_DEPENDENCY, TaskOutcome.UNFULFILLABLE}:
                patch = self.planner.create_or_revise(
                    request=PlanRequest(goal=goal, available_agents=available_agents, plan=self.store.get(plan_id))
                )
                if patch.tasks or patch.question or patch.decision.value in {"ask_user", "complete_plan", "fail_plan"}:
                    self.store.apply_patch(plan_id, patch, reason=result.outcome.value)
        yield OrchestratorEvent(type="max_steps", plan_id=plan_id)


class SqlDeterministicOrchestrator:
    """Production adapter: the graph and attempts are persisted in SQL.

    It intentionally keeps the same state machine as the in-memory harness,
    but every claim/result/failure is committed through ``SqlPlanStore``.
    """

    def __init__(self, *, store: SqlPlanStore, planner: Planner, executor: TaskExecutor,
                 max_attempts: int = 3, retry_delay_seconds: int = 60,
                 observation_writer: Optional[RuntimeObservationWriter] = None,
                 budget_service: Optional[RuntimeBudgetService] = None,
                 logging_level: str = "brief") -> None:
        self.store, self.planner, self.executor = store, planner, executor
        self.max_attempts = max(1, max_attempts)
        self.retry_delay_seconds = max(1, retry_delay_seconds)
        self.observation_writer = observation_writer
        self.budget_service = budget_service
        self.logging_level = logging_level

    async def run(self, *, plan_id: UUID, goal: str, available_agents: list[dict[str, Any]],
                  max_steps: int = 80, planner_kwargs: Optional[Dict[str, Any]] = None) -> AsyncIterator[OrchestratorEvent]:
        plan = await self.store.snapshot(plan_id)
        root_run_id = UUID(str(plan["root_run_id"]))
        iteration_number = 0

        async def observe(event_type: str, *, entity_type: str, entity_id: str, parent_type: Optional[str] = None, parent_id: Optional[str] = None, payload: Optional[Dict[str, Any]] = None, trigger: Optional[str] = None) -> None:
            if self.observation_writer is None:
                return
            await self.observation_writer.append(RuntimeObservationEvent(
                run_id=root_run_id, event_type=event_type, entity_type=entity_type,
                entity_id=entity_id, parent_entity_type=parent_type,
                parent_entity_id=parent_id, trigger=trigger,
                logging_level=self.logging_level, payload=payload or {},
            ))
        planner_kwargs = planner_kwargs or {}
        limits = dict(planner_kwargs.get("runtime_limits") or {})
        llm_kwargs = {
            key: planner_kwargs[key]
            for key in ("chat_id", "tenant_id", "user_id", "agent_run_id", "sandbox_overrides")
            if key in planner_kwargs
        }

        async def revise(*, reason: str, last_failure: Optional[Dict[str, Any]] = None) -> None:
            current = await self.store.snapshot(plan_id)
            invocation_id = uuid4()
            checkpoint_id = f"{root_run_id}:checkpoint:{invocation_id}"
            await observe("orchestrator_checkpoint_started", entity_type="orchestrator_checkpoint", entity_id=checkpoint_id,
                          parent_type="orchestrator", parent_id=f"{root_run_id}:orchestrator",
                          payload={"kind": "planner", "mode": "replan", "reason": reason, "revision": current["revision"]}, trigger=reason)
            self.store.session.add(RuntimePlannerInvocation(
                id=invocation_id, run_id=root_run_id, orchestrator_id=f"{root_run_id}:orchestrator",
                plan_id=plan_id, trigger=reason, status="running", revision_before=current["revision"],
                context_snapshot={"goal": goal, "last_failure": last_failure},
            ))
            await self.store.session.flush()
            await observe("planner_invocation_started", entity_type="planner_invocation", entity_id=str(invocation_id), parent_type="orchestrator", parent_id=f"{root_run_id}:orchestrator", payload={"trigger": reason, "revision": current["revision"]}, trigger=reason)
            patch = await self.planner.plan(request=PlanRequest(
                goal=goal,
                available_agents=available_agents,
                plan=current,
                last_failure=last_failure,
                trigger=reason,
                run_id=root_run_id,
                plan_id=plan_id,
                trace_parent_id=checkpoint_id,
            ), **llm_kwargs)
            decision = await self.budget_service.consume(run_id=root_run_id, owner_type="run", owner_id=str(root_run_id), metric="plan_revisions", limit=limits.get("plan_revisions"), reason=reason) if self.budget_service else None
            if decision is not None and not decision.allowed:
                raise RuntimeError("plan revision budget exceeded")
            updated = await self.store.apply_patch(plan_id, patch, reason=reason, planner_invocation_id=str(invocation_id))
            invocation = await self.store.session.get(RuntimePlannerInvocation, invocation_id, with_for_update=True)
            if invocation:
                invocation.status, invocation.revision_after, invocation.finished_at = "completed", updated.revision, datetime.now(timezone.utc)
            await observe("plan_patch_applied", entity_type="plan", entity_id=str(plan_id), parent_type="orchestrator", parent_id=f"{root_run_id}:orchestrator", payload={"revision": updated.revision, "patch": patch.model_dump(mode="json")}, trigger=reason)
            await observe("orchestrator_checkpoint_finished", entity_type="orchestrator_checkpoint", entity_id=checkpoint_id,
                          parent_type="orchestrator", parent_id=f"{root_run_id}:orchestrator",
                          payload={"kind": "planner", "mode": "replan", "status": "completed", "revision": updated.revision}, trigger=reason)
        if not plan["tasks"]:
            invocation_id = uuid4()
            checkpoint_id = f"{root_run_id}:checkpoint:{invocation_id}"
            await observe("orchestrator_checkpoint_started", entity_type="orchestrator_checkpoint", entity_id=checkpoint_id,
                          parent_type="orchestrator", parent_id=f"{root_run_id}:orchestrator",
                          payload={"kind": "planner", "mode": "initial", "revision": plan["revision"]}, trigger="initial")
            self.store.session.add(RuntimePlannerInvocation(
                id=invocation_id, run_id=root_run_id, orchestrator_id=f"{root_run_id}:orchestrator",
                plan_id=plan_id, trigger="initial", status="running", revision_before=plan["revision"], context_snapshot={"goal": goal},
            ))
            await self.store.session.flush()
            await observe("planner_invocation_started", entity_type="planner_invocation", entity_id=str(invocation_id), parent_type="orchestrator", parent_id=f"{root_run_id}:orchestrator", payload={"trigger": "initial", "revision": plan["revision"]}, trigger="initial")
            iteration_id = f"{root_run_id}:iteration:{iteration_number}"
            planner_executor_id = f"{iteration_id}:executor:planner"
            yield OrchestratorEvent(type="planner_iteration_start", entity_id=iteration_id,
                                    planner_iteration_id=iteration_id, parent_entity_type="orchestrator",
                                    parent_entity_id=f"{root_run_id}:orchestrator", iteration=iteration_number, mode="initial")
            yield OrchestratorEvent(type="agent_start", entity_id=planner_executor_id,
                                    agent_run_id=planner_executor_id, parent_entity_type="planner_iteration",
                                    parent_entity_id=iteration_id, agent_slug="planner", role="planner",
                                    executor_type="planner", executor_name="Планер", task_title=goal)
            patch = await self.planner.plan(request=PlanRequest(
                goal=goal, available_agents=available_agents, plan=plan,
                trigger="initial", run_id=root_run_id, plan_id=plan_id,
                trace_parent_id=iteration_id,
            ), **llm_kwargs)
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
            await observe("plan_created", entity_type="plan", entity_id=str(plan_id), parent_type="agent_run", parent_id=planner_executor_id,
                          payload={"revision": 1, "mode": "initial", "patch": patch.model_dump(mode="json")}, trigger="initial")
            await observe("orchestrator_checkpoint_finished", entity_type="orchestrator_checkpoint", entity_id=checkpoint_id,
                          parent_type="orchestrator", parent_id=f"{root_run_id}:orchestrator",
                          payload={"kind": "planner", "mode": "initial", "status": "completed", "revision": 1}, trigger="initial")
            yield OrchestratorEvent(type="agent_end", entity_id=planner_executor_id,
                                    agent_run_id=planner_executor_id, parent_entity_type="planner_iteration",
                                    parent_entity_id=iteration_id, agent_slug="planner", role="planner", status="completed")
            yield OrchestratorEvent(type="planner_iteration_end", entity_id=iteration_id,
                                    planner_iteration_id=iteration_id, parent_entity_type="orchestrator",
                                    parent_entity_id=f"{root_run_id}:orchestrator", iteration=iteration_number, status="completed", mode="initial")
            yield OrchestratorEvent(type="plan_created", entity_type="plan", entity_id=str(plan_id),
                                    parent_entity_type="agent_run", parent_entity_id=planner_executor_id,
                                    plan_id=str(plan_id), revision=1, mode="initial",
                                    patch=patch.model_dump(mode="json"))
        for _ in range(max_steps):
            plan = await self.store.snapshot(plan_id)
            if plan["status"] in {"completed", "waiting_input", "failed", "cancelled"}:
                yield OrchestratorEvent(type="plan_terminal", plan_id=str(plan_id), status=plan["status"])
                return
            iteration_number += 1
            iteration_id = f"{root_run_id}:iteration:{iteration_number}"
            task = await self.store.claim_ready(plan_id)
            if task is None:
                yield OrchestratorEvent(type="plan_stalled", plan_id=str(plan_id))
                return
            task_id = task.task_id
            snapshot = await self.store.snapshot(plan_id)
            dependencies = {
                dep: snapshot["tasks"].get(dep, {}).get("result", {}).get("outputs", {})
                for dep in snapshot["tasks"].get(task_id, {}).get("depends_on", [])
            }
            request = TaskRequest(task_id=task_id, title=task.title, objective=task.objective,
                                  agent_slug=task.agent_slug, inputs=task.inputs or {},
                                  checkpoint=task.checkpoint or {}, dependency_outputs=dependencies)
            checkpoint_id = f"{root_run_id}:checkpoint:{task_id}:{task.attempts}"
            executor_id = f"{iteration_id}:executor:{task_id}:attempt:{task.attempts}"
            await observe("orchestrator_checkpoint_started", entity_type="orchestrator_checkpoint", entity_id=checkpoint_id,
                          parent_type="orchestrator_iteration", parent_id=iteration_id,
                          payload={"kind": "task", "task_id": task_id, "attempt": task.attempts, "agent_slug": task.agent_slug})
            await observe("task_started", entity_type="task", entity_id=task_id, parent_type="plan", parent_id=str(plan_id), payload={"attempt": task.attempts, "checkpoint_id": checkpoint_id})
            await observe("attempt_started", entity_type="attempt", entity_id=f"{task_id}:attempt:{task.attempts}", parent_type="task", parent_id=task_id, payload={"attempt": task.attempts})
            if self.budget_service is not None:
                decision = await self.budget_service.consume(run_id=root_run_id, owner_type="run", owner_id=str(root_run_id), metric="task_attempts", limit=limits.get("task_attempts"), reason="task_started")
                if not decision.allowed:
                    raise RuntimeError("task attempt budget exceeded")
            yield OrchestratorEvent(type="task_started", entity_type="task", entity_id=task_id,
                                    parent_entity_type="plan", parent_entity_id=str(plan_id),
                                    plan_id=str(plan_id), task_id=task_id, attempt=task.attempts)
            yield OrchestratorEvent(type="planner_iteration_start", entity_id=iteration_id,
                                    planner_iteration_id=iteration_id, parent_entity_type="orchestrator",
                                    parent_entity_id=f"{root_run_id}:orchestrator", iteration=iteration_number,
                                    mode="execute_tasks")
            yield OrchestratorEvent(type="agent_start", entity_id=executor_id, agent_run_id=executor_id,
                                    parent_entity_type="planner_iteration", parent_entity_id=iteration_id,
                                    agent_slug=task.agent_slug, task_id=task_id, attempt=task.attempts,
                                    task_title=task.title, task_objective=task.objective,
                                    executor_type="agent", executor_name=task.agent_slug,
                                    task_inputs=task.inputs or {}, expected_outputs=[
                                        item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                                        for item in (task.expected_outputs or [])
                                    ])
            try:
                task_executor_kwargs = dict(planner_kwargs)
                task_executor_kwargs["runtime_run_id"] = str(root_run_id)
                task_executor_kwargs["lifecycle_agent_run_id"] = executor_id
                task_executor_kwargs["iteration_id"] = iteration_id
                result = await self.executor.execute_task(request=request, **task_executor_kwargs)
            except Exception as exc:
                failure = TaskAttemptFailure(code=type(exc).__name__, message=str(exc) or "task execution failed", retryable=True)
                await self.store.record_failure(plan_id, task_id, failure,
                    retry_at=datetime.now(timezone.utc) + timedelta(seconds=self.retry_delay_seconds),
                    max_attempts=self.max_attempts)
                await observe("attempt_failed", entity_type="attempt", entity_id=f"{task_id}:attempt:{task.attempts}", parent_type="task", parent_id=task_id, payload={"error": failure.model_dump(mode="json")}, trigger="technical_failure")
                await observe("orchestrator_checkpoint_finished", entity_type="orchestrator_checkpoint", entity_id=checkpoint_id,
                              parent_type="orchestrator", parent_id=f"{root_run_id}:orchestrator",
                              payload={"kind": "task", "task_id": task_id, "attempt": task.attempts, "status": "failed_technical", "error": failure.model_dump(mode="json")}, trigger="technical_failure")
                yield OrchestratorEvent(type="agent_end", entity_id=executor_id, agent_run_id=executor_id,
                                        parent_entity_type="planner_iteration", parent_entity_id=iteration_id,
                                        agent_slug=task.agent_slug, task_id=task_id, status="failed",
                                        task_title=task.title, task_objective=task.objective)
                yield OrchestratorEvent(type="task_attempt_failed", plan_id=str(plan_id), task_id=task_id,
                                        error=failure.model_dump(mode="json"))
                if not failure.retryable or task.attempts >= self.max_attempts:
                    await revise(reason="technical_failure", last_failure=failure.model_dump(mode="json"))
                continue
            await self.store.apply_result(plan_id, task_id, result)
            result_event = "task_completed" if result.outcome.value == "completed" else "task_unfulfillable" if result.outcome.value == "unfulfillable" else "task_paused"
            await observe(result_event, entity_type="task", entity_id=task_id, parent_type="plan", parent_id=str(plan_id), payload={"outcome": result.outcome.value, "summary": result.summary, "outputs": result.outputs}, trigger=result.outcome.value)
            await observe("attempt_succeeded", entity_type="attempt", entity_id=f"{task_id}:attempt:{task.attempts}", parent_type="task", parent_id=task_id, payload={"outcome": result.outcome.value})
            await observe("orchestrator_checkpoint_finished", entity_type="orchestrator_checkpoint", entity_id=checkpoint_id,
                          parent_type="orchestrator", parent_id=f"{root_run_id}:orchestrator",
                          payload={"kind": "task", "task_id": task_id, "attempt": task.attempts, "status": result.outcome.value, "summary": result.summary}, trigger=result.outcome.value)
            yield OrchestratorEvent(type="agent_end", entity_id=executor_id, agent_run_id=executor_id,
                                    parent_entity_type="planner_iteration", parent_entity_id=iteration_id,
                                    agent_slug=task.agent_slug, task_id=task_id,
                                    task_title=task.title, task_objective=task.objective,
                                    outcome=result.outcome.value,
                                    status="completed" if result.outcome.value == "completed" else result.outcome.value)
            yield OrchestratorEvent(type="planner_iteration_end", entity_id=iteration_id,
                                    planner_iteration_id=iteration_id, parent_entity_type="orchestrator",
                                    parent_entity_id=f"{root_run_id}:orchestrator", iteration=iteration_number,
                                    status="completed" if result.outcome.value == "completed" else result.outcome.value)
            yield OrchestratorEvent(type=("task_completed" if result.outcome.value == "completed" else "task_unfulfillable"),
                                    entity_type="task", entity_id=task_id,
                                    parent_entity_type="plan", parent_entity_id=str(plan_id),
                                    plan_id=str(plan_id), task_id=task_id, outcome=result.outcome.value)
            if result.outcome in {TaskOutcome.NEEDS_DEPENDENCY, TaskOutcome.UNFULFILLABLE}:
                await revise(reason=result.outcome.value)
        yield OrchestratorEvent(type="max_steps", plan_id=str(plan_id))
